# NeverStop Motion Coach

面向跑步与游泳的移动端 AI 动作分析 MVP。用户上传训练视频后，产品通过关键帧、动作指标和大众化建议解释“发生了什么、为什么值得注意、下次怎么练”。

## 当前版本

- 移动端优先的 React + TypeScript H5。
- 跑步 / 游泳视频拖入或选择，以及本机真实解析流程。
- OpenCV 视频抽帧、MediaPipe 33 点姿态识别和专项基础指标。
- 由真实关键点生成的证据帧；无法稳定识别时明确失败，不返回模拟结论。
- 可切换证据帧、指标、训练建议的完整报告。
- 历史动作分与能力变化对比。
- 手动运动记录、设备数据与文件导入入口。
- 匿名报告与手动运动记录保存在当前浏览器。
- 登录和第三方数据同步已预留接口边界。

演示报告中的数值明确标注为演示数据，不代表真实视频分析结果。

## 本地运行

首次安装：

```bash
pnpm install
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
```

分别启动分析服务和 H5：

```bash
pnpm api
pnpm dev -- --port 4173
```

访问 `http://127.0.0.1:4173/`。分析 API 位于 `http://127.0.0.1:8000/`，上传的原视频会在任务结束后删除，证据帧保存在本机 `backend/data/`（该目录不进入 Git）。

构建与检查：

```bash
pnpm lint
pnpm build
pnpm test:api
```

设计规范见 [DESIGN.md](./DESIGN.md)，技术边界见 [docs/architecture.md](./docs/architecture.md)。

## 影像素材

原型中的跑步与游泳照片来自 Unsplash，仅用于界面和证据标注演示：

- Running photo by an Unsplash contributor: `photo-1696536823512-79d724454616`
- Swimming photo from Unsplash: `photo-1494908817628-3944b78f0326`
