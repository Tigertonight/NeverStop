import runnerImage from '../assets/runner.jpg'
import swimmerImage from '../assets/swimmer.jpg'
import type { AnalysisReport, DataSource, WorkoutRecord } from '../types/domain'

export const reports: AnalysisReport[] = [
  {
    id: 'run-0710',
    source: 'demo',
    sport: 'running',
    title: '户外跑 · 动作分析',
    date: '今天 07:42',
    duration: '02:18 视频',
    score: 82,
    headline: '节奏稳定，落地点可以更靠近身体',
    summary: '你的步频保持得不错。疲劳后右脚会稍微落在身体前方，容易让推进变成刹车。下一次先把步幅收小一点。',
    image: runnerImage,
    metrics: [
      { label: '平均步频', value: '174', unit: '步/分', delta: '稳定区间', tone: 'positive' },
      { label: '触地位置', value: '+9', unit: '厘米', delta: '略靠前', tone: 'warning' },
      { label: '左右对称', value: '94', unit: '%', delta: '比上次 +2%', tone: 'positive' },
      { label: '身体前倾', value: '6.2', unit: '°', delta: '自然', tone: 'neutral' },
    ],
    insights: [
      { id: 'landing', title: '右脚落得离身体有点远', summary: '在 01:36，右脚先伸到髋部前方再落地，后半程更明显。', impact: '每一步都会多一点“刹车感”，腿要额外用力才能继续向前。', action: '下次慢跑时做 3 组 30 秒小步快跑，只想一件事：脚往身体正下方放。', successCue: '脚步声会更轻，落地时脚掌就在髋部下方，不会有向前够地的感觉。', severity: 'focus', timestamp: '01:36', marker: 'A' },
      { id: 'posture', title: '上半身角度保持得不错', summary: '肩膀和髋部大部分时间一起向前，没有明显弯腰。', impact: '身体能顺着跑动方向前进，不会把力量浪费在上下起伏上。', action: '继续放松肩颈，手肘自然向身后摆，不需要刻意挺胸。', successCue: '胸口放松、视线自然向前，腰部没有被折住的紧张感。', severity: 'good', timestamp: '00:48', marker: 'B' },
      { id: 'arms', title: '跑累后右手会摆到身体中间', summary: '最后 20 秒，右手有两次越过胸口中线。', impact: '手臂横着摆会带动上身左右晃，跑得越久越费力。', action: '下一次把手掌想成沿身体两侧的轨道前后移动，手肘只往身后送。', successCue: '肩膀不会左右扭，双手始终从裤缝旁经过。', severity: 'observe', timestamp: '01:58', marker: 'C' },
    ],
  },
  {
    id: 'swim-0706',
    source: 'demo',
    sport: 'swimming',
    title: '自由泳 · 动作分析',
    date: '7月6日 19:16',
    duration: '01:44 视频',
    score: 76,
    headline: '身体线条顺，前伸时双手可以再打开一点',
    summary: '身体保持得比较平直，前伸节奏也很连贯。双手偶尔会向头部中线靠近，下一次试着让手掌沿肩膀正前方入水。',
    image: swimmerImage,
    metrics: [
      { label: '划频', value: '31', unit: '次/分', delta: '节奏均匀', tone: 'positive' },
      { label: '身体线条', value: '90', unit: '%', delta: '较稳定', tone: 'positive' },
      { label: '前伸宽度', value: '8', unit: '厘米', delta: '略窄', tone: 'warning' },
      { label: '动作一致性', value: '88', unit: '%', delta: '可继续提升', tone: 'neutral' },
    ],
    insights: [
      { id: 'reach', title: '手入水时太靠近头部中间', summary: '在 00:52，手掌向头部中线靠近，而不是落在肩膀正前方。', impact: '身体会被手臂带着左右扭，后续抱水也更难找到稳定支点。', action: '下次做 4 趟轻松游，想象肩膀前方各有一条轨道，手掌沿自己的轨道入水。', successCue: '入水后头部保持不动，身体不会因为一只手入水而左右摇摆。', severity: 'focus', timestamp: '00:52', marker: 'A' },
      { id: 'line', title: '身体大部分时间能贴近水面', summary: '从肩膀到髋部没有明显下坡，腿部也没有持续拖在后面。', impact: '迎水面积更小，同样的划水力量可以游得更远。', action: '继续眼看池底，让后脑勺和背部保持放松，不要主动抬头找前方。', successCue: '能感觉臀部靠近水面，脚后跟偶尔轻轻打到水面。', severity: 'good', timestamp: '00:31', marker: 'B' },
    ],
  },
]

export const workouts: WorkoutRecord[] = [
  { id: 'w1', sport: 'running', date: '今天', distance: '5.20 km', duration: '28:14', source: 'video' },
  { id: 'w2', sport: 'swimming', date: '7月6日', distance: '1,000 m', duration: '24:38', source: 'manual' },
  { id: 'w3', sport: 'running', date: '7月2日', distance: '4.80 km', duration: '27:51', source: 'device' },
]

export const dataSources: DataSource[] = [
  { id: 'apple', name: 'Apple 健康', status: 'native_required', detail: '需要后续 iPhone App 授权' },
  { id: 'garmin', name: 'Garmin', status: 'web_oauth', detail: '规划通过网页授权与 FIT 文件接入' },
  { id: 'health-connect', name: 'Health Connect', status: 'native_required', detail: '需要后续 Android App 授权' },
  { id: 'keep', name: 'Keep / 其他平台', status: 'planned', detail: '预留文件导入，不依赖非公开接口' },
]
