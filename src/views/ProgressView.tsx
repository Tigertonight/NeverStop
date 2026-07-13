import { useMemo, useState } from 'react'
import { Activity, ArrowRight, HeartPulse, TrendingUp } from 'lucide-react'
import { SectionHeading, SportSelector, TopBar } from '../components/ui'
import type { AnalysisReport, Sport } from '../types/domain'

// 每个运动用一个「主指标」画趋势折线（越低越好，图上换算为越高越好的百分位分数）
const PRIMARY_KEY: Record<Sport, string> = { running: 'ankleOffsetRatio', swimming: 'headDeviation' }

interface TrendPoint {
  date: string
  value: number
}

function toTrendPoints(reports: AnalysisReport[], key: string): TrendPoint[] {
  return reports
    .map((report) => {
      const measurement = report.keyMeasurements?.[key]
      if (!measurement || typeof measurement.value !== 'number') return null
      return { date: report.trainingDate ?? report.createdAt ?? '', value: measurement.value }
    })
    .filter((point): point is TrendPoint => point !== null)
}

export function ProgressView({ allReports, onOpenReports }: { allReports: AnalysisReport[]; onOpenReports: () => void }) {
  const [sport, setSport] = useState<Sport>('running')

  const analysis = useMemo(() => {
    const reports = allReports
      .filter((report) => report.source === 'video' && report.sport === sport)
      .sort((a, b) => (a.trainingDate ?? a.createdAt ?? '').localeCompare(b.trainingDate ?? b.createdAt ?? ''))
    const primary = toTrendPoints(reports, PRIMARY_KEY[sport])
    return { reports, primary }
  }, [allReports, sport])

  const hasEnough = analysis.primary.length >= 2

  // 收集所有出现过的测量项，比较首末两次，给出「进步/稳定/关注」
  const highlights = useMemo(() => {
    const first = analysis.reports.find((r) => r.keyMeasurements)
    const last = [...analysis.reports].reverse().find((r) => r.keyMeasurements)
    if (!first || !last || first.id === last.id) return []
    const rows: Array<{ key: string; label: string; unit: string; delta: number; direction: 'improved' | 'stable' | 'regressed' }> = []
    for (const [key, cur] of Object.entries(last.keyMeasurements ?? {})) {
      const prev = first.keyMeasurements?.[key]
      if (!prev) continue
      const delta = cur.value - prev.value
      const denom = Math.abs(prev.value) > 1e-6 ? Math.abs(prev.value) : 1
      let direction: 'improved' | 'stable' | 'regressed' = 'stable'
      if (Math.abs(delta) / denom >= 0.05) {
        const lowerIsBetter = cur.betterWhen !== 'higher'
        direction = (lowerIsBetter ? delta < 0 : delta > 0) ? 'improved' : 'regressed'
      }
      rows.push({ key, label: cur.label, unit: cur.unit, delta, direction })
    }
    return rows
  }, [analysis.reports])

  if (!hasEnough) {
    return (
      <div className="view progress-view">
        <TopBar title="进步" />
        <main>
          <SportSelector value={sport} onChange={setSport} />
          <section className="empty-state">
            <TrendingUp size={30} />
            <h2>还没有足够的{sport === 'running' ? '跑步' : '游泳'}训练可对比</h2>
            <p>完成至少 2 次同类分析后，这里会显示你的关键指标趋势和进步变化。</p>
            <button className="text-button inline-link" onClick={onOpenReports}>去分析或查看报告 <ArrowRight size={15} /></button>
          </section>
        </main>
      </div>
    )
  }

  // 主指标折线：越低越好，映射为「越高越好」的展示分（0-100，取相对首末归一）
  const values = analysis.primary.map((p) => p.value)
  const vMax = Math.max(...values)
  const vMin = Math.min(...values)
  const range = vMax - vMin || 1
  const scores = values.map((v) => Math.round((1 - (v - vMin) / range) * 100)) // 值越小分越高
  const points = scores.map((score, index) => `${(index / Math.max(1, scores.length - 1)) * 100},${90 - (score / 100) * 72}`).join(' ')
  const latestScore = scores.at(-1)!
  const firstScore = scores[0]

  return (
    <div className="view progress-view">
      <TopBar title="进步" />
      <main>
        <SportSelector value={sport} onChange={setSport} />
        <section className={`progress-score ${sport}`}>
          <span>近 {values.length} 次 · {PRIMARY_KEY[sport] === 'ankleOffsetRatio' ? '脚踝前伸控制' : '头位稳定度'}</span>
          <div className="score-change">
            <strong>{latestScore}</strong>
            <span className={latestScore >= firstScore ? '' : 'down'}><TrendingUp size={15} /> {latestScore - firstScore >= 0 ? '+' : ''}{latestScore - firstScore} 分</span>
          </div>
          <div className="line-chart">
            <svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="关键指标趋势">
              <line x1="0" y1="25" x2="100" y2="25" /><line x1="0" y1="55" x2="100" y2="55" /><line x1="0" y1="85" x2="100" y2="85" />
              <polyline points={points} />
              {scores.map((score, index) => <circle key={index} cx={(index / Math.max(1, scores.length - 1)) * 100} cy={90 - (score / 100) * 72} r="1.8" />)}
            </svg>
            <div className="chart-labels"><span>最早</span><span>最近</span></div>
          </div>
          <small className="progress-note">分数由该指标的相对变化换算，越高代表控制越好；仅供自我对照，非绝对评分。</small>
        </section>

        {highlights.length ? (
          <section className="progress-highlights">
            <SectionHeading title="首末对比变化" />
            {highlights.map((row) => (
              <div key={row.key} className="highlight-row">
                <span className={`highlight-icon ${row.direction === 'improved' ? 'positive' : row.direction === 'regressed' ? 'warning' : 'neutral'}`}>
                  {row.direction === 'improved' ? <TrendingUp size={19} /> : row.direction === 'regressed' ? <HeartPulse size={19} /> : <Activity size={19} />}
                </span>
                <div>
                  <strong>{row.label}</strong>
                  <p>{row.delta >= 0 ? '+' : ''}{row.delta.toFixed(2)}{row.unit}（首次 → 最近）</p>
                </div>
                <span className={`delta ${row.direction === 'improved' ? 'positive' : row.direction === 'regressed' ? 'warning' : ''}`}>
                  {row.direction === 'improved' ? '进步' : row.direction === 'regressed' ? '关注' : '稳定'}
                </span>
              </div>
            ))}
          </section>
        ) : null}
      </main>
    </div>
  )
}
