import { useState } from 'react'
import { Activity, ArrowRight, HeartPulse, TrendingUp } from 'lucide-react'
import { DemoNotice, SectionHeading, SportSelector, TopBar } from '../components/ui'
import type { Sport } from '../types/domain'

export function ProgressView({ onOpenReports }: { onOpenReports: () => void }) {
  const [sport, setSport] = useState<Sport>('running')
  const values = sport === 'running' ? [68, 71, 70, 76, 78, 82] : [62, 66, 69, 73, 72, 76]
  const max = Math.max(...values)
  const min = Math.min(...values)
  const points = values.map((value, index) => `${index * 20},${90 - ((value - 55) / 35) * 72}`).join(' ')
  return (
    <div className="view progress-view">
      <TopBar title="进步" />
      <main><DemoNotice compact /><SportSelector value={sport} onChange={setSport} />
        <section className={`progress-score ${sport}`}><span>示例 · 近 6 次动作分</span><div className="score-change"><strong>{values.at(-1)}</strong><span><TrendingUp size={15} /> +{values.at(-1)! - values[0]} 分</span></div><div className="line-chart"><svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="示例动作分趋势"><line x1="0" y1="25" x2="100" y2="25" /><line x1="0" y1="55" x2="100" y2="55" /><line x1="0" y1="85" x2="100" y2="85" /><polyline points={points} />{values.map((value, index) => <circle key={index} cx={index * 20} cy={90 - ((value - 55) / 35) * 72} r="1.8" />)}</svg><div className="chart-labels"><span>示例起点</span><span>示例当前</span></div></div></section>
        <section className="progress-highlights"><SectionHeading title="示例变化解读" />
          <div className="highlight-row"><span className="highlight-icon positive"><TrendingUp size={19} /></span><div><strong>{sport === 'running' ? '触地点更接近身体' : '前伸方向更稳定'}</strong><p>{sport === 'running' ? '触地点前伸距离从 15 cm 降到 9 cm' : '手掌向中线靠近的距离减少了 6 cm'}</p></div><span className="delta positive">进步</span></div>
          <div className="highlight-row"><span className="highlight-icon neutral"><Activity size={19} /></span><div><strong>{sport === 'running' ? '步频保持稳定' : '划频基本稳定'}</strong><p>{sport === 'running' ? '近 4 次都在 170–176 步/分' : '近 4 次都在 29–32 次/分'}</p></div><span className="delta">稳定</span></div>
          <div className="highlight-row"><span className="highlight-icon warning"><HeartPulse size={19} /></span><div><strong>{sport === 'running' ? '疲劳后摆臂仍需留意' : '后半程髋部略有下沉'}</strong><p>连续训练中仍有改善空间</p></div><span className="delta warning">关注</span></div>
        </section>
        <section className="compare-band"><div><span className="eyebrow">示例最佳表现</span><h2>{max} 分</h2><p>相比最低分提升 {max - min} 分</p><button className="text-button inline-link" onClick={onOpenReports}>查看示例报告 <ArrowRight size={15} /></button></div><div className="comparison-bars"><span style={{ height: `${min}%` }}><i>{min}</i></span><span className="current" style={{ height: `${max}%` }}><i>{max}</i></span><div><small>首次</small><small>现在</small></div></div></section>
      </main>
    </div>
  )
}
