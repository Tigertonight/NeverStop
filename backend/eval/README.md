# 离线评测 (ALG-001)

在带标签的视频片段上运行真实分析管线（`backend.analyzer.analyze_video`），
量化**运动识别准确率**、**混淆矩阵**、**置信度 / 检测率 / 拍摄质量分布**，
用于回归防退化，也为算法调参提供客观基线。

> 所有指标均为二维姿态的可观测统计，**不构成医疗诊断**。
> 内置合成样本只验证管线连通与回归，数值不代表真实运动学测量。

## 运行

```bash
# 1) 内置合成样本（无需任何外部数据，用于冒烟 / CI 连通性）
pnpm eval:api
#   等价于 .venv/bin/python -m backend.eval.run_eval

# 2) 使用真实带标签片段
.venv/bin/python -m backend.eval.run_eval --manifest data/eval/manifest.json

# 3) 输出机器可读结果 + CI 门禁（准确率低于阈值则非零退出）
.venv/bin/python -m backend.eval.run_eval \
  --manifest data/eval/manifest.json \
  --json out/eval.json \
  --min-accuracy 0.9
```

## manifest 格式

`manifest.json` 中所有相对 `path` 以该文件所在目录为基准：

```json
{
  "clips": [
    { "path": "clips/run_side_01.mp4", "sport": "running",  "note": "侧面固定机位·晴天" },
    { "path": "clips/swim_free_02.mp4", "sport": "swimming", "note": "泳池侧拍·自由泳" }
  ]
}
```

- `sport`：真实标签，必须是 `running` 或 `swimming`。
- `path`：视频文件路径（需满足上传校验：mp4、时长 10–180s、分辨率 120–4096、帧率 5–240）。
- `note`：可选，仅用于结果可读性。

真实片段需**获得录制对象授权**后再纳入评测集，且不提交进仓库
（见 DATA-002）。建议放在 `data/eval/`（已 gitignore 数据目录）或仓库外目录。

## 固定回归测试视频

`backend/eval/manifest.json` 已登记一个本机固定测试片段（蛙泳，绝对路径，未入库）：

```bash
.venv/bin/python -m backend.eval.run_eval --manifest backend/eval/manifest.json
```

- 期望结果：识别为 `swimming`，被正确分类（accuracy=100%）。
- 该 manifest 指向本机 `IMG_4005.MOV` 的绝对路径（约 84MB，不入库，仅在本机有效）；
  换机器时请更新 manifest 里的 `path` 或改用相对路径 + 授权片段。


## 输出解读

- **accuracy**：在“成功产出报告”的片段上，预测运动与真实标签一致的比例。
- **confusion**：行是真实标签，列是预测结果；`rejected` 列表示被
  `AnalysisError`（如 `SPORT_MISMATCH` / `SPORT_UNRECOGNIZED` / `POSE_NOT_DETECTED`）拒绝的片段。
  被拒绝的片段不计入 accuracy 分母。
- **capture_quality**：来自 ALG-002 的拍摄质量分级（`good` / `limited` / `unusable`），
  用于观察数据集画质构成，定位“低质量导致的拒绝/误判”。

## CI 集成

`--min-accuracy` 提供硬门禁：低于阈值以退出码 1 结束，可直接接入 GitHub Actions。
无 manifest（仅合成样本）时不建议开启门禁，因为合成样本仅验证连通性。

## 抽帧率消融实验 (ALG-002)

判断「当前视频抽帧率是否最优」的实证工具。当前采样策略是**按时长自适应的目标采样帧率**（非固定比例）：

| 视频时长 | 目标采样帧率 |
|---------|------------|
| ≤30s | 10 fps |
| 30–60s | 8 fps |
| >60s | 5 fps |

再乘以时长得抽帧数，并 clamp 到 `[40, 600]` 帧后用 `linspace` 均匀取帧。
即较长视频抽得更稀；600 帧的硬上限意味着 >40s@15fps 会被截到实际约 12fps。

`sample_rate_ablation.py` 对同一视频扫描多个采样率，以**最高采样率结果为参照**，
观察关键运动信号（headDeviation / kneeFlexion / bodyIssue 等）与泳姿分类
相对参照的偏差随采样率下降如何变化，找出「偏差收敛的最低采样率」= 性价比拐点。

```bash
.venv/bin/python -m backend.eval.sample_rate_ablation \
  --manifest backend/eval/manifest.json \
  --rates 3 5 8 10 12 15 \
  --json backend/eval/ablation_report.json
```

### 实测结论（IMG_4005.MOV，48s@30fps，蛙泳）

| 采样率 | 抽帧数 | 检测率 | 泳姿 | armSync | 相对12fps最大信号偏差 | 耗时 |
|-------|-------|-------|------|---------|-------------------|------|
| 3 fps | 145 | 0.828 | breaststroke | 0.312 | 29.5% | 6.0s |
| 5 fps | 242 | 0.839 | breaststroke | 0.310 | 9.6% | 6.3s |
| **8 fps（当前）** | 386 | 0.858 | breaststroke | 0.357 | 6.3% | 7.3s |
| 10 fps | 483 | 0.857 | breaststroke | 0.365 | 14.1% | 8.0s |
| 12 fps | 579 | 0.860 | breaststroke | 0.352 | — (参照) | 9.9s |

- **泳姿分类**在 ≥3fps 全部与最高档一致（分类对采样率不敏感）。
- **运动信号**在 **5fps 就基本收敛**（偏差 <10%），当前 8fps 已在收敛区、留有余量。
- **3fps 明显失真**（偏差 29.5%），不可取。
- 提高到 10–12fps 边际收益很小（检测率仅 +0.2%），却增加约 35% 耗时。

**判断：当前自适应采样率（这段 48s 视频取 8fps）接近最优**——处于信号收敛区，
再降会失真、再升性价比低。若要更省时，40–60s 档可下探到 6fps；但不建议低于 5fps。

对应回归测试见 `backend/tests/test_analyzer.py::SampleRateTest`：
- `test_default_sample_fps_tiers`：固化采样率分档。
- `test_override_changes_sample_density`：验证采样率可调。
- `test_current_rate_is_at_or_above_convergence`（有 manifest 才跑）：
  实证当前采样率处于收敛区（提高 1.5× 采样率检测率提升 ≤10%）。
