import { useEffect, useRef, useState, type ChangeEvent, type DragEvent } from 'react'
import { useSearchParams } from 'react-router-dom'
import { AlertTriangle, ArrowRight, Camera, Check, FileVideo2, Gauge, RefreshCcw, RotateCcw, ShieldCheck, Sparkles, Upload, Zap } from 'lucide-react'
import { DemoNotice, ScoreRing, SectionHeading, SportIcon, SportSelector, TopBar } from '../components/ui'
import { AnalysisApiError, analysisApiHost, createAnalysisJob, getAnalysisJob, getAnalysisReport } from '../lib/analysis-api'
import { reports } from '../data/demo'
import type { AnalysisReport, Sport } from '../types/domain'

type AnalysisPhase = 'idle' | 'validating' | 'ready' | 'analyzing' | 'done'

/** 分析失败的分类，决定提示文案与可否原样重试。 */
type AnalysisFailure = {
  message: string
  hint: string
  /** connection: 服务未连上，可直接重试；rejected: 视频本身不合适，需换视频；server: 服务异常，可稍后重试。 */
  kind: 'connection' | 'rejected' | 'server'
}

/** 视频不适合分析、需要用户更换的错误码（重试无意义）。 */
const REJECT_CODES = new Set(['SPORT_MISMATCH', 'SPORT_NOT_SUPPORTED', 'NO_POSE_DETECTED', 'INSUFFICIENT_MOTION', 'VIDEO_TOO_SHORT'])

function classifyFailure(error: unknown, jobErrorCode?: string | null): AnalysisFailure {
  const message = error instanceof Error ? error.message : '视频分析失败，请重新尝试。'
  if (error instanceof AnalysisApiError && error.status === undefined) {
    return { kind: 'connection', message: '无法连接本地分析服务。', hint: `请确认分析服务已在 ${analysisApiHost()} 启动后重试。` }
  }
  if (jobErrorCode && REJECT_CODES.has(jobErrorCode)) {
    return { kind: 'rejected', message, hint: '这段视频不适合本次分析，请按拍摄建议换一段视频。' }
  }
  if (error instanceof AnalysisApiError && error.status && error.status >= 500) {
    return { kind: 'server', message: '分析服务出现异常。', hint: '请稍后重试；若持续失败可重启本机分析服务。' }
  }
  return { kind: 'server', message, hint: '可重新开始分析，或更换一段视频。' }
}

export function AnalyzeView({ onReportReady, onOpenReport }: { onReportReady: (report: AnalysisReport) => void; onOpenReport: (report: AnalysisReport) => void }) {
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
  const [analysisFailure, setAnalysisFailure] = useState<AnalysisFailure | null>(null)
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
    setAnalysisFailure(null)
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
    setAnalysisFailure(null)
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
    setAnalysisFailure(null)
    setAnalysisStage('正在上传视频')
    setProgress(3)
    setPhase('analyzing')
    let jobErrorCode: string | null = null
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
      if (job.status === 'failed' || !job.reportId) {
        jobErrorCode = job.errorCode ?? null
        throw new Error(job.errorMessage ?? '没有生成可用报告，请重新尝试。')
      }
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
      setAnalysisFailure(classifyFailure(error, jobErrorCode))
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
            <div className="video-frame"><video src={videoUrl} controls playsInline preload="metadata" /><span className={`sport-badge ${sport}`}><SportIcon sport={sport} size={14} />{sport === 'running' ? '跑步' : '自动识别泳姿'}</span></div>
            <div className="file-row"><FileVideo2 size={20} /><div><strong>{fileName}</strong><span>将在本机分析服务中抽帧并识别姿态</span></div><Check size={18} className="success" /></div>
            {validationError ? <div className="form-error standalone" role="alert">{validationError}</div> : null}
            {analysisFailure ? (
              <div className={`analysis-failure ${analysisFailure.kind}`} role="alert">
                <AlertTriangle size={18} />
                <div><strong>{analysisFailure.message}</strong><p>{analysisFailure.hint}</p></div>
              </div>
            ) : null}
            {analysisFailure?.kind === 'rejected' ? (
              <button className="primary-button wide" onClick={() => inputRef.current?.click()}><Upload size={18} /> 更换视频</button>
            ) : (
              <button className="primary-button wide" onClick={startAnalysis}>{analysisFailure ? <><RefreshCcw size={18} /> 重试分析</> : <><Sparkles size={18} /> 开始真实分析</>}</button>
            )}
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
