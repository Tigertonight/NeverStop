import { Activity, ArrowRight, Footprints, Sparkles, Waves } from 'lucide-react'
import { ReportPreview, SectionHeading, TopBar, WorkoutRow } from '../components/ui'
import { getGreeting } from '../lib/format'
import { reports } from '../data/demo'
import type { AnalysisReport, Sport, WorkoutRecord } from '../types/domain'

export function HomeView({ workouts, onAnalyze, onOpenReport, onOpenReports, onProfile, latestReport }: {
  workouts: WorkoutRecord[]
  onAnalyze: (sport: Sport) => void
  onOpenReport: (report: AnalysisReport) => void
  onOpenReports: () => void
  onProfile: () => void
  latestReport?: AnalysisReport
}) {
  return (
    <div className="view home-view">
      <TopBar action={<button className="avatar-button" aria-label="个人中心" onClick={onProfile}>N</button>} />
      <main>
        <section className="home-intro">
          <p>{getGreeting()}，运动者</p>
          <h1>看懂动作，<br />练得更轻松。</h1>
        </section>

        <section className="quick-analysis">
          <div className="quick-copy">
            <span className="ai-label"><Sparkles size={14} /> AI 动作分析</span>
            <h2>上传一段训练视频</h2>
            <p>从关键帧里找到最值得调整的一件事。</p>
          </div>
          <div className="sport-actions">
            <button className="sport-action running" onClick={() => onAnalyze('running')}>
              <span className="sport-action-icon"><Footprints size={24} /></span><span><strong>分析跑步</strong><small>侧面拍摄效果更好</small></span><ArrowRight size={19} />
            </button>
            <button className="sport-action swimming" onClick={() => onAnalyze('swimming')}>
              <span className="sport-action-icon"><Waves size={24} /></span><span><strong>分析游泳</strong><small>自动识别泳姿并分析</small></span><ArrowRight size={19} />
            </button>
          </div>
        </section>

        <section className="section-block">
          <SectionHeading title={latestReport ? '最新视频报告' : '体验示例报告'} action={<button className="text-button" onClick={onOpenReports}>查看全部</button>} />
          <ReportPreview report={latestReport ?? reports[0]} onOpen={() => onOpenReport(latestReport ?? reports[0])} />
        </section>

        <section className="section-block">
          <SectionHeading title="我的运动记录" action={<button className="text-button" onClick={onProfile}>管理记录</button>} />
          {workouts.length === 0 ? (
            <div className="empty-state compact-empty"><span><Activity size={22} /></span><div><strong>还没有本地记录</strong><p>手动记录第一场训练，之后会在这里形成趋势。</p></div></div>
          ) : (
            <div className="workout-list">
              {workouts.slice(0, 3).map((workout) => <WorkoutRow key={workout.id} workout={workout} />)}
            </div>
          )}
        </section>
      </main>
    </div>
  )
}
