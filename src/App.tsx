import { useEffect, useMemo, useRef, useState, type ChangeEvent, type DragEvent, type FormEvent, type ReactNode } from 'react'
import { Navigate, Route, Routes, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import {
  Activity,
  ArrowLeft,
  ArrowRight,
  BarChart3,
  Camera,
  Check,
  ChevronRight,
  CircleUserRound,
  FileVideo2,
  Footprints,
  Gauge,
  HeartPulse,
  Home,
  Info,
  Link2,
  LockKeyhole,
  Plus,
  RotateCcw,
  Share2,
  ShieldCheck,
  Sparkles,
  TimerReset,
  TrendingUp,
  Upload,
  Waves,
  X,
  Zap,
} from 'lucide-react'
import { dataSources, reports } from './data/demo'
import { createAnalysisJob, getAnalysisJob, getAnalysisReport } from './lib/analysis-api'
import { loadLocalReports, persistLocalReports } from './lib/report-storage'
import { loadLocalWorkouts, persistLocalWorkouts } from './lib/workout-storage'
import type { AnalysisReport, AppTab, Insight, Sport, WorkoutRecord } from './types/domain'

const tabPaths: Record<AppTab, string> = {
  home: '/',
  analyze: '/analyze',
  progress: '/progress',
  profile: '/me',
}

const navItems: Array<{ id: AppTab; label: string; icon: typeof Home }> = [
  { id: 'home', label: '首页', icon: Home },
  { id: 'analyze', label: '分析', icon: Camera },
  { id: 'progress', label: '进步', icon: BarChart3 },
  { id: 'profile', label: '我的', icon: CircleUserRound },
]

function getGreeting() {
  const hour = new Date().getHours()
  if (hour < 6) return '夜深了'
  if (hour < 12) return '上午好'
  if (hour < 18) return '下午好'
  return '晚上好'
}

function todayValue() {
  const date = new Date()
  const offset = date.getTimezoneOffset() * 60_000
  return new Date(date.getTime() - offset).toISOString().slice(0, 10)
}

function formatWorkoutDate(value: string) {
  if (value === todayValue() || value === '今天') return '今天'
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
  return match ? `${Number(match[2])}月${Number(match[3])}日` : value
}

function SportIcon({ sport, size = 18 }: { sport: Sport; size?: number }) {
  return sport === 'running' ? <Footprints size={size} /> : <Waves size={size} />
}

function Brand() {
  return (
    <div className="brand" aria-label="NeverStop">
      <span className="brand-mark"><span /></span>
      <span className="brand-name">NeverStop</span>
    </div>
  )
}

function TopBar({ title, action, onBack }: { title?: string; action?: ReactNode; onBack?: () => void }) {
  return (
    <header className="topbar">
      <div className="topbar-leading">
        {onBack ? (
          <button className="icon-button quiet" onClick={onBack} aria-label="返回" title="返回">
            <ArrowLeft size={20} />
          </button>
        ) : title ? null : <Brand />}
        {title ? <h1>{title}</h1> : null}
      </div>
      {action ?? null}
    </header>
  )
}

function BottomNav({ active, onChange }: { active: AppTab; onChange: (tab: AppTab) => void }) {
  return (
    <nav className="bottom-nav" aria-label="主导航">
      {navItems.map(({ id, label, icon: Icon }) => (
        <button key={id} className={active === id ? 'active' : ''} onClick={() => onChange(id)} aria-current={active === id ? 'page' : undefined}>
          <Icon size={21} strokeWidth={active === id ? 2.5 : 2} />
          <span>{label}</span>
        </button>
      ))}
    </nav>
  )
}

function SideNav({ active, onChange }: { active: AppTab; onChange: (tab: AppTab) => void }) {
  return (
    <aside className="side-nav">
      <Brand />
      <nav aria-label="主导航">
        {navItems.map(({ id, label, icon: Icon }) => (
          <button key={id} className={active === id ? 'active' : ''} onClick={() => onChange(id)}>
            <Icon size={20} />
            <span>{label}</span>
          </button>
        ))}
      </nav>
      <div className="side-foot">
        <div className="avatar">N</div>
        <div><strong>运动者</strong><span>匿名本地账号</span></div>
      </div>
    </aside>
  )
}

function DemoNotice({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`demo-notice ${compact ? 'compact' : ''}`}>
      <Info size={16} />
      <div><strong>当前为交互演示</strong><span>结果来自示例数据，不代表对上传视频的真实判断。</span></div>
    </div>
  )
}

function ScoreRing({ score, compact = false, isDemo = true }: { score: number; compact?: boolean; isDemo?: boolean }) {
  return (
    <div className={`score-ring ${compact ? 'compact' : ''}`} style={{ '--score-deg': `${score * 3.6}deg` } as React.CSSProperties}>
      <div><strong>{score}</strong><span>{isDemo ? '示例分' : '动作分'}</span></div>
    </div>
  )
}

function EvidenceOverlay({ sport, insight }: { sport: Sport; insight?: Insight }) {
  return (
    <div className={`measurement-overlay ${sport}`} aria-hidden="true">
      {sport === 'running' ? (
        <>
          <span className="measurement-anchor hip-anchor" />
          <span className="reference-axis" />
          <span className="distance-line" />
          <span className="measurement-anchor landing-anchor" />
          <span className="measurement-label">落地点 +9 cm</span>
        </>
      ) : (
        <>
          <span className="reach-bracket" />
          <span className="measurement-label">前伸宽度 8 cm</span>
        </>
      )}
      <span className="measurement-marker">{insight?.marker ?? 'A'}</span>
    </div>
  )
}

function ReportPreview({ report, onOpen }: { report: AnalysisReport; onOpen: () => void }) {
  const isDemo = report.source === 'demo'
  return (
    <button className="report-preview" onClick={onOpen} aria-label={`查看${report.title}`}>
      <div className="report-thumb">
        <img src={report.image} alt={`${report.sport === 'running' ? '跑步' : '游泳'}${isDemo ? '示例' : '视频'}证据帧`} />
        {isDemo ? <EvidenceOverlay sport={report.sport} insight={report.insights[0]} /> : null}
        <span className={`sport-badge ${report.sport}`}><SportIcon sport={report.sport} size={14} />{report.sport === 'running' ? '跑步' : '游泳'}</span>
        <span className={`media-demo-label ${isDemo ? '' : 'real'}`}>{isDemo ? '示例' : '真实视频'}</span>
      </div>
      <div className="report-preview-body">
        <div><span className="eyebrow">{isDemo ? '示例报告' : '视频报告'} · {report.date}</span><h3>{report.headline}</h3></div>
        <div className="report-score"><strong>{isDemo ? report.score : report.insights.length}</strong><span>{isDemo ? '示例分' : '个关键时刻'}</span></div>
      </div>
      <div className="report-link">查看{isDemo ? '示例' : '完整'}报告 <ChevronRight size={17} /></div>
    </button>
  )
}

function SectionHeading({ title, action }: { title: string; action?: ReactNode }) {
  return <div className="section-heading"><h2>{title}</h2>{action}</div>
}

function HomeView({ workouts, onAnalyze, onOpenReport, onOpenReports, onProfile, latestReport }: {
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
              <span className="sport-action-icon"><Waves size={24} /></span><span><strong>分析游泳</strong><small>泳池侧面完整入镜</small></span><ArrowRight size={19} />
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

function SportSelector({ value, onChange }: { value: Sport; onChange: (sport: Sport) => void }) {
  return (
    <div className="segmented" role="tablist" aria-label="运动类型">
      <button className={value === 'running' ? 'active' : ''} onClick={() => onChange('running')} role="tab" aria-selected={value === 'running'}><Footprints size={17} /> 跑步</button>
      <button className={value === 'swimming' ? 'active' : ''} onClick={() => onChange('swimming')} role="tab" aria-selected={value === 'swimming'}><Waves size={17} /> 游泳</button>
    </div>
  )
}

type AnalysisPhase = 'idle' | 'validating' | 'ready' | 'analyzing' | 'done'

function AnalyzeView({ onReportReady, onOpenReport }: { onReportReady: (report: AnalysisReport) => void; onOpenReport: (report: AnalysisReport) => void }) {
  const [searchParams, setSearchParams] = useSearchParams()
  const initialSport = searchParams.get('sport') === 'swimming' ? 'swimming' : 'running'
  const [sport, setSport] = useState<Sport>(initialSport)
  const [phase, setPhase] = useState<AnalysisPhase>('idle')
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [fileName, setFileName] = useState('')
  const [videoUrl, setVideoUrl] = useState('')
  const [progress, setProgress] = useState(0)
  const [analysisStage, setAnalysisStage] = useState('')
  const [completedReport, setCompletedReport] = useState<AnalysisReport | null>(null)
  const [isDemoAnalysis, setIsDemoAnalysis] = useState(false)
  const [validationError, setValidationError] = useState('')
  const [isDragging, setIsDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const timerRef = useRef<number | null>(null)
  const dragDepthRef = useRef(0)
  const runRef = useRef(0)

  useEffect(() => () => {
    if (videoUrl) URL.revokeObjectURL(videoUrl)
    if (timerRef.current) window.clearInterval(timerRef.current)
    runRef.current += 1
  }, [videoUrl])

  const clearAnalysisState = () => {
    if (videoUrl) URL.revokeObjectURL(videoUrl)
    if (timerRef.current) window.clearInterval(timerRef.current)
    setVideoUrl('')
    setFileName('')
    setSelectedFile(null)
    setProgress(0)
    setAnalysisStage('')
    setCompletedReport(null)
    setIsDemoAnalysis(false)
    setValidationError('')
    setIsDragging(false)
    dragDepthRef.current = 0
    setPhase('idle')
  }

  const reset = () => {
    clearAnalysisState()
    setSearchParams({ sport }, { replace: true })
  }

  const chooseSport = (nextSport: Sport) => {
    setSport(nextSport)
    clearAnalysisState()
    setSearchParams({ sport: nextSport })
  }

  const processVideoFile = (file: File) => {
    setValidationError('')
    const hasSupportedExtension = /\.(mp4|mov)$/i.test(file.name)
    if (!['video/mp4', 'video/quicktime'].includes(file.type) && !hasSupportedExtension) {
      setValidationError('暂不支持此格式，请选择 MP4 或 MOV 视频。')
      return
    }
    if (file.size > 300 * 1024 * 1024) {
      setValidationError('视频超过 300 MB，请压缩或截取后再试。')
      return
    }

    setPhase('validating')
    if (videoUrl) URL.revokeObjectURL(videoUrl)
    const nextUrl = URL.createObjectURL(file)
    const metadataVideo = document.createElement('video')
    metadataVideo.preload = 'metadata'
    metadataVideo.onloadedmetadata = () => {
      const duration = metadataVideo.duration
      if (duration < 10 || duration > 180) {
        URL.revokeObjectURL(nextUrl)
        setPhase('idle')
        setValidationError('请选择 10 秒至 3 分钟的视频。')
        return
      }
      setVideoUrl(nextUrl)
      setFileName(file.name)
      setSelectedFile(file)
      setPhase('ready')
    }
    metadataVideo.onerror = () => {
      URL.revokeObjectURL(nextUrl)
      setPhase('idle')
      setValidationError('无法读取视频，请确认文件没有损坏。')
    }
    metadataVideo.src = nextUrl
  }

  const handleFile = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (file) processVideoFile(file)
  }

  const handleDragEnter = (event: DragEvent<HTMLElement>) => {
    event.preventDefault()
    event.stopPropagation()
    if (phase !== 'idle') return
    dragDepthRef.current += 1
    setIsDragging(true)
  }

  const handleDragOver = (event: DragEvent<HTMLElement>) => {
    event.preventDefault()
    event.stopPropagation()
    if (phase === 'idle') event.dataTransfer.dropEffect = 'copy'
  }

  const handleDragLeave = (event: DragEvent<HTMLElement>) => {
    event.preventDefault()
    event.stopPropagation()
    if (phase !== 'idle') return
    dragDepthRef.current = Math.max(0, dragDepthRef.current - 1)
    if (dragDepthRef.current === 0) setIsDragging(false)
  }

  const handleDrop = (event: DragEvent<HTMLElement>) => {
    event.preventDefault()
    event.stopPropagation()
    dragDepthRef.current = 0
    setIsDragging(false)
    if (phase !== 'idle') return
    const files = Array.from(event.dataTransfer.files)
    if (files.length !== 1) {
      setValidationError(files.length === 0 ? '没有检测到视频文件，请重新拖入。' : '一次只能分析一个视频。')
      return
    }
    processVideoFile(files[0])
  }

  const startExample = () => {
    setIsDemoAnalysis(true)
    setCompletedReport(report)
    setFileName(`NeverStop ${sport === 'running' ? '跑步' : '游泳'}示例`)
    setPhase('analyzing')
    setProgress(8)
    let next = 8
    timerRef.current = window.setInterval(() => {
      next += next < 48 ? 9 : next < 78 ? 6 : 4
      if (next >= 100) {
        window.clearInterval(timerRef.current ?? undefined)
        setProgress(100)
        window.setTimeout(() => {
          setPhase('done')
          setSearchParams({ sport, result: 'done' }, { replace: true })
        }, 350)
        return
      }
      setProgress(next)
    }, 320)
  }

  const startAnalysis = async () => {
    if (!selectedFile) return
    const currentRun = ++runRef.current
    setIsDemoAnalysis(false)
    setValidationError('')
    setAnalysisStage('正在上传视频')
    setProgress(3)
    setPhase('analyzing')
    try {
      let job = await createAnalysisJob(selectedFile, sport)
      while (job.status !== 'completed' && job.status !== 'failed') {
        if (runRef.current !== currentRun) return
        setProgress(job.progress)
        setAnalysisStage(job.stage ?? '正在分析视频')
        await new Promise((resolve) => window.setTimeout(resolve, 650))
        job = await getAnalysisJob(job.id)
      }
      if (runRef.current !== currentRun) return
      if (job.status === 'failed' || !job.reportId) throw new Error(job.errorMessage ?? '没有生成可用报告，请重新尝试。')
      const nextReport = await getAnalysisReport(job.reportId)
      if (runRef.current !== currentRun) return
      setCompletedReport(nextReport)
      onReportReady(nextReport)
      setProgress(100)
      setAnalysisStage('分析完成')
      setPhase('done')
      setSearchParams({ sport, result: nextReport.id }, { replace: true })
    } catch (error) {
      if (runRef.current !== currentRun) return
      setPhase('ready')
      setProgress(0)
      setValidationError(error instanceof Error ? error.message : '视频分析失败，请重新尝试。')
    }
  }

  const report = sport === 'running' ? reports[0] : reports[1]

  return (
    <div className="view analyze-view">
      <TopBar title="动作分析" action={phase !== 'idle' ? <button className="icon-button quiet" onClick={reset} aria-label="重新选择视频" title="重新选择"><RotateCcw size={19} /></button> : undefined} />
      <main>
        <SportSelector value={sport} onChange={chooseSport} />
        {isDemoAnalysis ? <DemoNotice compact /> : null}

        {phase === 'idle' || phase === 'validating' ? (
          <>
            <section
              className={`upload-zone ${phase === 'validating' ? 'is-validating' : ''} ${isDragging ? 'is-dragging' : ''}`}
              onClick={() => phase === 'idle' && inputRef.current?.click()}
              onDragEnter={handleDragEnter}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
            >
              <input ref={inputRef} type="file" accept="video/mp4,video/quicktime" onChange={handleFile} hidden />
              <div className={`upload-visual ${sport}`}><SportIcon sport={sport} size={34} /><span className="scan-line" /></div>
              <h2>{phase === 'validating' ? '正在检查视频' : isDragging ? '松开即可添加视频' : `拖入或选择一段${sport === 'running' ? '跑步' : '游泳'}视频`}</h2>
              <p>{phase === 'validating' ? '确认格式、大小和视频时长' : isDragging ? '一次添加一个 MP4 或 MOV 文件' : '支持 MP4、MOV，10 秒至 3 分钟，最大 300 MB'}</p>
              <button className="primary-button" type="button" disabled={phase === 'validating'} onClick={(event) => { event.stopPropagation(); inputRef.current?.click() }}><Upload size={18} /> 选择视频</button>
            </section>
            {validationError ? <div className="form-error standalone" role="alert">{validationError}</div> : null}
            <button className="secondary-button wide example-button" onClick={startExample}><Sparkles size={17} /> 不上传，体验示例分析</button>

            <section className="capture-guide">
              <SectionHeading title="这样拍，分析更准确" />
              <div className="guide-grid">
                <div><span><Camera size={19} /></span><strong>保持全身入镜</strong><p>固定机位，不要跟随移动</p></div>
                <div><span><Gauge size={19} /></span><strong>{sport === 'running' ? '从侧面拍摄' : '平行泳道拍摄'}</strong><p>{sport === 'running' ? '距离跑道约 4–6 米' : '尽量拍到完整划水周期'}</p></div>
                <div><span><Zap size={19} /></span><strong>光线保持充足</strong><p>避免逆光和人物遮挡</p></div>
              </div>
            </section>
          </>
        ) : null}

        {phase === 'ready' ? (
          <section className="video-ready">
            <div className="video-frame"><video src={videoUrl} controls playsInline preload="metadata" /><span className={`sport-badge ${sport}`}><SportIcon sport={sport} size={14} />{sport === 'running' ? '跑步' : '游泳'}</span></div>
            <div className="file-row"><FileVideo2 size={20} /><div><strong>{fileName}</strong><span>将在本机分析服务中抽帧并识别姿态</span></div><Check size={18} className="success" /></div>
            {validationError ? <div className="form-error standalone" role="alert">{validationError}</div> : null}
            <button className="primary-button wide" onClick={startAnalysis}><Sparkles size={18} /> 开始真实分析</button>
            <button className="secondary-button wide" onClick={() => inputRef.current?.click()}><RotateCcw size={17} /> 重新选择</button>
            <input ref={inputRef} type="file" accept="video/mp4,video/quicktime" onChange={handleFile} hidden />
          </section>
        ) : null}

        {phase === 'analyzing' ? (
          <section className="analysis-progress">
            <div className="analysis-stage">
              {isDemoAnalysis ? <img src={report.image} alt="正在运行的示例分析" /> : <video src={videoUrl} muted autoPlay loop playsInline />}
              <div className="analysis-grid" /><span className="scan-bar" />
              <span className={`media-demo-label large ${isDemoAnalysis ? '' : 'real'}`}>{isDemoAnalysis ? '模拟分析' : '本机解析'}</span>
            </div>
            <div className="progress-copy">
              <span>{progress}% · {isDemoAnalysis ? '演示' : '真实视频'}</span>
              <h2>{isDemoAnalysis ? (progress < 40 ? '识别身体关键点' : progress < 75 ? '拆解动作节奏' : '生成训练建议') : analysisStage}</h2>
              <p>{isDemoAnalysis ? (progress < 40 ? '演示逐帧定位肩、髋、膝和脚踝' : progress < 75 ? '演示对比动作周期与左右稳定性' : '把示例指标转成容易执行的建议') : '正在抽取关键帧、估计身体关键点并计算动作指标'}</p>
              <div className="progress-track"><span style={{ width: `${progress}%` }} /></div>
            </div>
            <div className="privacy-note"><ShieldCheck size={17} /> {isDemoAnalysis ? '本次只在浏览器中模拟，不会上传视频' : '视频仅发送到本机 127.0.0.1 分析，完成后自动删除原文件'}</div>
          </section>
        ) : null}

        {phase === 'done' ? (
          <section className="analysis-complete">
            <div className="complete-icon"><Check size={28} /></div><span className="eyebrow">{isDemoAnalysis ? '模拟分析完成 · 示例结果' : '视频解析完成 · 真实结果'}</span>
            <h2>{(completedReport ?? report).headline}</h2>{isDemoAnalysis ? <ScoreRing score={(completedReport ?? report).score} /> : null}<p>{(completedReport ?? report).summary}</p>
            <button className="primary-button wide" onClick={() => onOpenReport(completedReport ?? report)}>查看{isDemoAnalysis ? '示例' : '完整'}报告 <ArrowRight size={18} /></button>
            <button className="secondary-button wide" onClick={reset}>分析另一段视频</button>
          </section>
        ) : null}
      </main>
    </div>
  )
}

function ReportDetail({ report, onBack, onToast }: { report: AnalysisReport; onBack: () => void; onToast: (message: string) => void }) {
  const [activeInsight, setActiveInsight] = useState(report.insights[0])
  const evidenceRef = useRef<HTMLElement | null>(null)
  const isDemo = report.source === 'demo'
  const activeEvidenceIndex = Math.max(0, report.insights.findIndex((insight) => insight.id === activeInsight.id))
  const evidenceProgress = report.insights.length <= 1 ? 100 : activeEvidenceIndex / (report.insights.length - 1) * 100

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
          <div className="report-meta"><span className={`sport-tag ${report.sport}`}><SportIcon sport={report.sport} size={15} />{report.sport === 'running' ? '跑步' : '游泳'}</span><span>{isDemo ? '示例报告' : '真实视频报告'}</span><span>{report.duration}</span></div>
          <div className={`report-title-row ${isDemo ? '' : 'without-score'}`}><div><span className="eyebrow">AI 动作总结{isDemo ? '示例' : ''}</span><h1>{report.headline}</h1></div>{isDemo ? <ScoreRing score={report.score} compact /> : null}</div>
          <p>{report.summary}</p>
          {isDemo ? <div className="score-method"><span><strong>评分维度</strong>稳定性、对称性、专项动作</span><span><strong>结果置信度</strong>示例数据，不提供真实置信度</span></div> : null}
        </section>

        <section className="evidence-section" ref={evidenceRef}>
          <SectionHeading title="关键证据" action={<span className="demo-pill">{isDemo ? '示例关键帧' : '视频关键帧'}</span>} />
          <div className="evidence-viewer">
            <img src={activeInsight.image ?? report.image} alt={`${report.title}${isDemo ? '示例' : '视频'}关键动作帧 ${activeInsight.marker}`} />{isDemo ? <EvidenceOverlay sport={report.sport} insight={activeInsight} /> : null}
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
          </div>
        </section>

        {isDemo ? <section className="metric-section"><SectionHeading title="动作数据" /><div className="metric-grid">
          {report.metrics.map((metric) => <div className="metric-tile" key={metric.label}><span>{metric.label}</span><strong>{metric.value}<small>{metric.unit}</small></strong><p className={metric.tone}>{metric.tone === 'positive' ? <TrendingUp size={13} /> : metric.tone === 'warning' ? <Activity size={13} /> : null}{metric.delta}</p></div>)}
        </div></section> : null}

        <section className="insight-section"><SectionHeading title={isDemo ? '先练这几件事' : '教练建议'} /><div className="insight-list">
          {report.insights.map((insight, index) => <button key={insight.id} className="insight-row" onClick={() => { setActiveInsight(insight); window.scrollTo({ top: Math.max(0, (evidenceRef.current?.offsetTop ?? 80) - 72), behavior: 'smooth' }) }}><span className={`insight-number ${insight.severity}`}>{index + 1}</span><div><strong>{insight.title}</strong><p><b>练法：</b>{insight.action}</p><small>证据 {insight.marker} · {insight.timestamp}{insight.successCue ? ` · 做对：${insight.successCue}` : ''}</small></div><ChevronRight size={18} /></button>)}
        </div></section>

        <section className="next-session"><div><span className="eyebrow">下次只练这一件</span><h2>{report.insights[0].title}</h2><p>{report.insights[0].action}</p><small>判断做对：{report.insights[0].successCue ?? '动作更顺畅，并且不需要额外用力补偿。'}</small></div><TimerReset size={34} /></section>
        <p className="report-disclaimer">{isDemo ? '本报告为交互演示，仅用于展示产品结构，' : '本报告基于视频关键点估算，'}不构成医疗诊断或治疗建议。</p>
      </main>
    </div>
  )
}

function ReportsView({ allReports, onOpenReport, onBack }: { allReports: AnalysisReport[]; onOpenReport: (report: AnalysisReport) => void; onBack: () => void }) {
  const [sport, setSport] = useState<'all' | Sport>('all')
  const visibleReports = useMemo(() => sport === 'all' ? allReports : allReports.filter((report) => report.sport === sport), [sport, allReports])
  return (
    <div className="view reports-view">
      <TopBar title="动作报告" onBack={onBack} />
      <main><div className="filter-chips">
        <button className={sport === 'all' ? 'active' : ''} onClick={() => setSport('all')}>全部</button>
        <button className={sport === 'running' ? 'active' : ''} onClick={() => setSport('running')}><Footprints size={15} />跑步</button>
        <button className={sport === 'swimming' ? 'active' : ''} onClick={() => setSport('swimming')}><Waves size={15} />游泳</button>
      </div><div className="report-list">{visibleReports.map((report) => <ReportPreview key={report.id} report={report} onOpen={() => onOpenReport(report)} />)}</div></main>
    </div>
  )
}

function ProgressView({ onOpenReports }: { onOpenReports: () => void }) {
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

interface ManualRecordInput { sport: Sport; distance: number; minutes: number; seconds: number; date: string }

function ManualRecordModal({ onClose, onSave }: { onClose: () => void; onSave: (input: ManualRecordInput) => void }) {
  const [sport, setSport] = useState<Sport>('running')
  const [distance, setDistance] = useState('')
  const [minutes, setMinutes] = useState('')
  const [seconds, setSeconds] = useState('')
  const [date, setDate] = useState(todayValue())
  const [errors, setErrors] = useState<string[]>([])

  const submit = (event: FormEvent) => {
    event.preventDefault()
    const nextErrors: string[] = []
    const distanceValue = Number(distance)
    const minuteValue = Number(minutes)
    const secondValue = Number(seconds || 0)
    if (!distance || !Number.isFinite(distanceValue) || distanceValue <= 0) nextErrors.push('请输入有效距离')
    if (!minutes || !Number.isInteger(minuteValue) || minuteValue < 0) nextErrors.push('请输入有效分钟数')
    if (!Number.isInteger(secondValue) || secondValue < 0 || secondValue > 59) nextErrors.push('秒数应在 0–59 之间')
    if (minuteValue === 0 && secondValue === 0) nextErrors.push('运动时长必须大于 0')
    if (!date) nextErrors.push('请选择运动日期')
    if (date > todayValue()) nextErrors.push('运动日期不能晚于今天')
    if (nextErrors.length > 0) { setErrors(nextErrors); return }
    onSave({ sport, distance: distanceValue, minutes: minuteValue, seconds: secondValue, date })
  }

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.currentTarget === event.target) onClose() }}>
      <form className="modal-sheet" role="dialog" aria-modal="true" aria-labelledby="manual-title" onSubmit={submit}>
        <div className="modal-head"><h2 id="manual-title">手动记录运动</h2><button className="icon-button quiet" type="button" onClick={onClose} aria-label="关闭" title="关闭"><X size={20} /></button></div>
        <label><span>运动类型</span><select value={sport} onChange={(event) => { setSport(event.target.value as Sport); setDistance(''); setErrors([]) }}><option value="running">跑步</option><option value="swimming">游泳</option></select></label>
        <label><span>距离</span><div className="input-with-unit"><input value={distance} onChange={(event) => setDistance(event.target.value)} inputMode="decimal" placeholder={sport === 'running' ? '5.00' : '1000'} aria-label="距离" /><span>{sport === 'running' ? 'km' : 'm'}</span></div></label>
        <fieldset className="duration-fields"><legend>时长</legend><label><span>分钟</span><input value={minutes} onChange={(event) => setMinutes(event.target.value)} inputMode="numeric" placeholder="30" aria-label="分钟" /></label><label><span>秒</span><input value={seconds} onChange={(event) => setSeconds(event.target.value)} inputMode="numeric" placeholder="00" aria-label="秒" /></label></fieldset>
        <label><span>日期</span><input type="date" value={date} max={todayValue()} onChange={(event) => setDate(event.target.value)} /></label>
        {errors.length > 0 ? <div className="form-error" role="alert">{errors.join('；')}</div> : null}
        <button className="primary-button wide" type="submit">保存到本机</button>
        <p className="storage-note"><ShieldCheck size={14} /> 未登录记录仅保存在当前浏览器中</p>
      </form>
    </div>
  )
}

function WorkoutRow({ workout }: { workout: WorkoutRecord }) {
  return <div className="workout-row"><span className={`workout-icon ${workout.sport}`}><SportIcon sport={workout.sport} /></span><div><strong>{workout.distance}</strong><p>{formatWorkoutDate(workout.date)} · {workout.duration}</p></div><span className="source-label">{workout.source === 'manual' ? '本机' : workout.source === 'device' ? '设备' : '视频'}</span></div>
}

function ProfileView({ workouts, onSaveWorkout, onToast }: { workouts: WorkoutRecord[]; onSaveWorkout: (input: ManualRecordInput) => void; onToast: (message: string) => void }) {
  const [showManual, setShowManual] = useState(false)
  const sourceLabel = { native_required: '需 App', web_oauth: '可规划', planned: '规划中' } as const
  return (
    <div className="view profile-view">
      <TopBar title="我的" />
      <main>
        <section className="profile-header"><div className="profile-avatar">N</div><div><h1>运动者</h1><p>当前为匿名本地模式</p></div><button className="secondary-button compact" onClick={() => onToast('登录与跨设备同步将在账号模块接入后开放')}><LockKeyhole size={16} /> 登录后同步</button></section>
        <section className="record-actions">
          <button onClick={() => setShowManual(true)}><span><Plus size={20} /></span><div><strong>手动记录</strong><p>记录会保存在当前浏览器</p></div><ChevronRight size={18} /></button>
          <button onClick={() => onToast('FIT、GPX、TCX 文件导入正在规划中')}><span><Upload size={20} /></span><div><strong>导入运动文件</strong><p>FIT、GPX、TCX · 即将开放</p></div><ChevronRight size={18} /></button>
        </section>
        <section className="data-sources"><SectionHeading title="设备与数据" action={<span className="section-note">能力说明</span>} /><div className="source-list">
          {dataSources.map((source) => <button key={source.id} onClick={() => onToast(source.detail)}><span className={`source-logo ${source.id}`}><Link2 size={18} /></span><div><strong>{source.name}</strong><p>{source.detail}</p></div><span className={`source-status ${source.status}`}>{sourceLabel[source.status]}</span><ChevronRight size={17} /></button>)}
        </div></section>
        <section className="workout-records"><SectionHeading title="本地运动记录" />
          {workouts.length === 0 ? <div className="empty-state"><span><Activity size={22} /></span><div><strong>还没有记录</strong><p>添加第一场跑步或游泳，刷新页面也会保留。</p></div><button className="secondary-button compact" onClick={() => setShowManual(true)}>添加记录</button></div> : <div className="workout-list">{workouts.map((workout) => <WorkoutRow key={workout.id} workout={workout} />)}</div>}
        </section>
      </main>
      {showManual ? <ManualRecordModal onClose={() => setShowManual(false)} onSave={(input) => { onSaveWorkout(input); setShowManual(false) }} /> : null}
    </div>
  )
}

function Toast({ message }: { message: string }) {
  return <div className="toast" role="status"><Check size={16} />{message}</div>
}

function App() {
  const location = useLocation()
  const navigate = useNavigate()
  const [toast, setToast] = useState('')
  const [workouts, setWorkouts] = useState<WorkoutRecord[]>(loadLocalWorkouts)
  const [localReports, setLocalReports] = useState<AnalysisReport[]>(loadLocalReports)
  const toastTimer = useRef<number | null>(null)
  const allReports = useMemo(() => [...localReports, ...reports], [localReports])

  const activeTab: AppTab = location.pathname.startsWith('/analyze') ? 'analyze' : location.pathname.startsWith('/progress') || location.pathname.startsWith('/reports') ? 'progress' : location.pathname.startsWith('/me') ? 'profile' : 'home'

  const showToast = (message: string) => {
    if (toastTimer.current) window.clearTimeout(toastTimer.current)
    setToast(message)
    toastTimer.current = window.setTimeout(() => setToast(''), 2600)
  }

  const changeTab = (tab: AppTab) => {
    navigate(tabPaths[tab])
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const openReport = (report: AnalysisReport) => {
    navigate(`/reports/${report.id}`)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const saveReport = (report: AnalysisReport) => {
    setLocalReports((current) => {
      const next = [report, ...current.filter((item) => item.id !== report.id)]
      persistLocalReports(next)
      return next
    })
  }

  const saveWorkout = (input: ManualRecordInput) => {
    const totalSeconds = input.minutes * 60 + input.seconds
    const nextRecord: WorkoutRecord = {
      id: crypto.randomUUID(),
      sport: input.sport,
      date: input.date,
      distance: input.sport === 'running' ? `${input.distance.toFixed(2)} km` : `${Math.round(input.distance)} m`,
      duration: `${Math.floor(totalSeconds / 60).toString().padStart(2, '0')}:${(totalSeconds % 60).toString().padStart(2, '0')}`,
      source: 'manual',
    }
    setWorkouts((current) => {
      const next = [nextRecord, ...current]
      persistLocalWorkouts(next)
      return next
    })
    showToast('运动记录已保存到当前浏览器')
  }

  return (
    <div className="app-shell">
      <SideNav active={activeTab} onChange={changeTab} />
      <div className="app-content">
        <Routes>
          <Route path="/" element={<HomeView workouts={workouts} latestReport={localReports[0]} onAnalyze={(sport) => navigate(`/analyze?sport=${sport}`)} onOpenReport={openReport} onOpenReports={() => navigate('/reports')} onProfile={() => navigate('/me')} />} />
          <Route path="/analyze" element={<AnalyzeView onReportReady={saveReport} onOpenReport={openReport} />} />
          <Route path="/reports" element={<ReportsView allReports={allReports} onOpenReport={openReport} onBack={() => navigate('/progress')} />} />
          <Route path="/reports/:reportId" element={<ReportRoute allReports={allReports} onBack={() => navigate('/reports')} onToast={showToast} />} />
          <Route path="/progress" element={<ProgressView onOpenReports={() => navigate('/reports')} />} />
          <Route path="/me" element={<ProfileView workouts={workouts} onSaveWorkout={saveWorkout} onToast={showToast} />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </div>
      <BottomNav active={activeTab} onChange={changeTab} />
      {toast ? <Toast message={toast} /> : null}
    </div>
  )
}

function ReportRoute({ allReports, onBack, onToast }: { allReports: AnalysisReport[]; onBack: () => void; onToast: (message: string) => void }) {
  const { reportId } = useParams()
  const report = allReports.find((item) => item.id === reportId)
  return report ? <ReportDetail report={report} onBack={onBack} onToast={onToast} /> : <Navigate to="/reports" replace />
}

export default App
