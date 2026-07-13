import { useEffect, useRef, useState } from 'react'
import { Activity, Check, ChevronRight, Info, Share2, TimerReset, TrendingUp, X } from 'lucide-react'
import { DemoNotice, EvidenceOverlay, ScoreRing, SectionHeading, SportIcon, TopBar } from '../components/ui'
import { correctSwimStroke, submitInsightFeedback } from '../lib/analysis-api'
import { loadReportFeedback, persistInsightFeedback } from '../lib/feedback-storage'
import { formatReportDate } from '../lib/format'
import type { AnalysisReport } from '../types/domain'

export function ReportDetail({ report, onBack, onToast, onReanalyze }: { report: AnalysisReport; onBack: () => void; onToast: (message: string) => void; onReanalyze?: (report: AnalysisReport) => void }) {
  const [displayReport, setDisplayReport] = useState(report)
  const [activeInsight, setActiveInsight] = useState(report.insights[0])
  const [showStrokeChoices, setShowStrokeChoices] = useState(false)
  const [feedback, setFeedback] = useState<Record<string, string>>(() => loadReportFeedback(report.id))
  const evidenceRef = useRef<HTMLElement | null>(null)
  const isDemo = report.source === 'demo'
  const activeEvidenceIndex = Math.max(0, report.insights.findIndex((insight) => insight.id === activeInsight.id))
  const evidenceProgress = report.insights.length <= 1 ? 100 : activeEvidenceIndex / (report.insights.length - 1) * 100

  useEffect(() => {
    setDisplayReport(report)
    setActiveInsight(report.insights[0])
    setFeedback(loadReportFeedback(report.id))
  }, [report])

  const updateStroke = async (stroke: 'freestyle' | 'breaststroke' | 'backstroke' | 'butterfly') => {
    try {
      const next = await correctSwimStroke(report.id, stroke)
      setDisplayReport(next)
      setShowStrokeChoices(false)
      onToast('已记录泳姿修正，专项建议需重新分析后更新')
    } catch (error) {
      onToast(error instanceof Error ? error.message : '泳姿修正失败')
    }
  }

  const sendFeedback = async (value: 'accurate' | 'inaccurate' | 'unclear') => {
    try {
      await submitInsightFeedback(report.id, activeInsight.id, value)
      setFeedback((current) => ({ ...current, [activeInsight.id]: value }))
      persistInsightFeedback(report.id, activeInsight.id, value)
      onToast('反馈已记录')
    } catch (error) {
      onToast(error instanceof Error ? error.message : '反馈提交失败')
    }
  }

  const shareReport = async () => {
    const payload = { title: report.title, text: `NeverStop ${isDemo ? '示例' : '动作'}报告：${report.headline}`, url: window.location.href }
    try {
      if (navigator.share) await navigator.share(payload)
      else {
        await navigator.clipboard.writeText(`${payload.text} ${payload.url}`)
        onToast('报告链接已复制')
      }
    } catch {
      onToast('已取消分享')
    }
  }

  return (
    <div className="view report-detail">
      <TopBar title="动作报告" onBack={onBack} action={<button className="icon-button quiet" onClick={shareReport} aria-label="分享报告" title="分享"><Share2 size={19} /></button>} />
      <main>
        {isDemo ? <DemoNotice compact /> : null}
        <section className="report-hero">
          <div className="report-meta"><span className={`sport-tag ${displayReport.sport}`}><SportIcon sport={displayReport.sport} size={15} />{displayReport.sport === 'running' ? '跑步' : displayReport.swimStroke?.strokeName ?? '游泳'}</span>{displayReport.swimStroke ? <span>泳姿置信度 {displayReport.swimStroke.confidence}%</span> : null}<span>{isDemo ? '示例报告' : formatReportDate(displayReport)}</span><span>{report.duration}</span></div>
          {!isDemo && displayReport.swimStroke ? <div className="stroke-confirm"><span>识别泳姿是否正确？</span><button className="secondary-button compact" onClick={() => onToast('已确认当前泳姿') }><Check size={15} />正确</button><button className="text-button" onClick={() => setShowStrokeChoices((value) => !value)}>修改</button>{showStrokeChoices ? <div className="stroke-options">{([['freestyle', '自由泳'], ['breaststroke', '蛙泳'], ['backstroke', '仰泳'], ['butterfly', '蝶泳']] as const).map(([value, label]) => <button key={value} onClick={() => updateStroke(value)}>{label}</button>)}</div> : null}</div> : null}
          {displayReport.adviceNeedsReanalysis ? <div className="quality-warning reanalyze"><Info size={17} /><div><strong>泳姿已修正</strong><p>当前证据仍来自原分析。用原视频重新分析，即可生成对应泳姿的专项建议，无需重新上传。</p>{onReanalyze ? <button className="secondary-button compact" type="button" onClick={() => onReanalyze(displayReport)}><TimerReset size={15} />用原视频重新分析</button> : null}</div></div> : null}
          {report.qualityAssessment?.status === 'limited' ? <div className="quality-warning"><Info size={17} /><div><strong>本次证据有限</strong><p>{report.qualityAssessment.blockingIssues.join('；')}</p></div></div> : null}
          <div className={`report-title-row ${isDemo ? '' : 'without-score'}`}><div><span className="eyebrow">{isDemo ? 'AI 动作总结示例' : displayReport.displayName ?? 'AI 动作总结'}</span><h1>{report.headline}</h1></div>{isDemo ? <ScoreRing score={report.score} compact /> : null}</div>
          <p>{report.summary}</p>
          {isDemo ? <div className="score-method"><span><strong>评分维度</strong>稳定性、对称性、专项动作</span><span><strong>结果置信度</strong>示例数据，不提供真实置信度</span></div> : null}
        </section>

        <section className="evidence-section" ref={evidenceRef}>
          <SectionHeading title="关键证据" action={<span className="demo-pill">{isDemo ? '示例关键帧' : '视频关键帧'}</span>} />
          <div className="evidence-viewer">
            {activeInsight.clip && !isDemo ? <video key={activeInsight.clip} src={activeInsight.clip} poster={activeInsight.image ?? report.image} controls muted playsInline preload="metadata" /> : <img src={activeInsight.image ?? report.image} alt={`${report.title}${isDemo ? '示例' : '视频'}关键动作帧 ${activeInsight.marker}`} />}{isDemo ? <EvidenceOverlay sport={report.sport} insight={activeInsight} /> : null}
            <div className="frame-top"><span>{activeInsight.timestamp}</span><span>关键帧 {activeInsight.marker}</span></div>
          </div>
          <div className="timeline">
            <div className="timeline-track"><span style={{ width: `${evidenceProgress}%` }} /></div>
            <div className="timeline-markers">{report.insights.map((insight) => <button key={insight.id} className={activeInsight.id === insight.id ? 'active' : ''} onClick={() => setActiveInsight(insight)} aria-label={`查看证据 ${insight.marker}`}><span>{insight.marker}</span></button>)}</div>
          </div>
          <div className="active-evidence">
            <div className="evidence-problem"><span className={`severity-dot ${activeInsight.severity}`} /><div><span className="coach-label">你的视频里</span><strong>{activeInsight.title}</strong><p>{activeInsight.summary}</p></div></div>
            <div className="coach-guidance">
              <div><span className="coach-label">为什么要改</span><p>{activeInsight.impact ?? '这个动作会影响身体稳定和发力效率，需要在下一次训练中继续观察。'}</p></div>
              <div className="action"><span className="coach-label">下次这样做</span><p>{activeInsight.action}</p></div>
              <div className="success"><span className="coach-label">做对时的感觉</span><p>{activeInsight.successCue ?? '动作会更顺畅、更稳定，也不会需要额外用力补偿。'}</p></div>
            </div>
            {!isDemo ? <div className="evidence-feedback"><span>这条判断对你有帮助吗？</span><button className={feedback[activeInsight.id] === 'accurate' ? 'active' : ''} onClick={() => sendFeedback('accurate')}><Check size={15} />准确</button><button className={feedback[activeInsight.id] === 'inaccurate' ? 'active' : ''} onClick={() => sendFeedback('inaccurate')}><X size={15} />不准确</button><button className={feedback[activeInsight.id] === 'unclear' ? 'active' : ''} onClick={() => sendFeedback('unclear')}><Info size={15} />没看懂</button></div> : null}
          </div>
        </section>

        {isDemo ? <section className="metric-section"><SectionHeading title="动作数据" /><div className="metric-grid">
          {report.metrics.map((metric) => <div className="metric-tile" key={metric.label}><span>{metric.label}</span><strong>{metric.value}<small>{metric.unit}</small></strong><p className={metric.tone}>{metric.tone === 'positive' ? <TrendingUp size={13} /> : metric.tone === 'warning' ? <Activity size={13} /> : null}{metric.delta}</p></div>)}
        </div></section> : null}

        <section className="insight-section"><SectionHeading title={isDemo ? '先练这几件事' : '教练建议'} /><div className="insight-list">
          {report.insights.map((insight, index) => <button key={insight.id} className="insight-row" onClick={() => { setActiveInsight(insight); window.scrollTo({ top: Math.max(0, (evidenceRef.current?.offsetTop ?? 80) - 72), behavior: 'smooth' }) }}><span className={`insight-number ${insight.severity}`}>{index + 1}</span><div><strong>{insight.title}</strong><p><b>练法：</b>{insight.action}</p><small>证据 {insight.marker} · {insight.timestamp}{insight.successCue ? ` · 做对：${insight.successCue}` : ''}</small></div><ChevronRight size={18} /></button>)}
        </div></section>

        <section className="next-session"><div><span className="eyebrow">下次只练这一件</span><h2>{report.prescription?.focusCue ?? report.insights[0].title}</h2><p>{report.prescription?.drill ?? report.insights[0].action}</p><small>{report.prescription ? `${report.prescription.volume} · ${report.prescription.rest} · ` : ''}判断做对：{report.prescription?.successCue ?? report.insights[0].successCue ?? '动作更顺畅，并且不需要额外用力补偿。'}</small></div><TimerReset size={34} /></section>
        {!isDemo && report.comparison ? <section className="comparison-summary"><span className="eyebrow">历史对比</span><h2>{report.comparison.status === 'comparable' ? '已与最近一次同泳姿训练对齐' : '暂时没有可比较的历史训练'}</h2><p>{report.comparison.status === 'comparable' ? `${report.comparison.basis}。仍需关注 ${report.comparison.remaining?.length ?? 0} 项，新出现 ${report.comparison.newIssues?.length ?? 0} 项。` : report.comparison.reason}</p>{report.comparison.status === 'comparable' && report.comparison.metricTrends?.length ? <ul className="metric-trends">{report.comparison.metricTrends.map((trend) => { const tone = trend.direction === 'improved' ? 'up' : trend.direction === 'regressed' ? 'down' : 'flat'; const arrow = tone === 'up' ? '↑ 变好' : tone === 'down' ? '↓ 待关注' : '≈ 持平'; return <li key={trend.key} className={`metric-trend ${tone}`}><span className="metric-trend-label">{trend.label}</span><span className="metric-trend-values">{trend.previous.toFixed(2)}{trend.unit} → <strong>{trend.current.toFixed(2)}{trend.unit}</strong></span><span className="metric-trend-badge">{arrow}</span></li> })}</ul> : null}</section> : null}
        {!isDemo && report.modelReview ? <p className="ai-provenance">{report.modelReview.status === 'reviewed' ? '已通过 MiniMax 结构化复核' : '工程分析模式'} · {report.modelReview.reason}</p> : null}
        <p className="report-disclaimer">{isDemo ? '本报告为交互演示，仅用于展示产品结构，' : '本报告基于视频关键点估算，'}不构成医疗诊断或治疗建议。</p>
      </main>
    </div>
  )
}
