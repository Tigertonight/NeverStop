import { useEffect, useMemo, useRef, useState } from 'react'
import { Navigate, Route, Routes, useLocation, useNavigate, useParams } from 'react-router-dom'
import { BottomNav, SideNav, Toast } from './components/ui'
import { tabPaths } from './components/nav'
import { HomeView } from './views/HomeView'
import { AnalyzeView } from './views/AnalyzeView'
import { ReportDetail } from './views/ReportDetail'
import { ReportsView } from './views/ReportsView'
import { ProgressView } from './views/ProgressView'
import { ProfileView } from './views/ProfileView'
import { deleteAnalysisReport, getAnalysisReport, getAnalysisReports, updateAnalysisReport } from './lib/analysis-api'
import { loadLocalReports, persistLocalReports } from './lib/report-storage'
import { loadLocalWorkouts, persistLocalWorkouts } from './lib/workout-storage'
import { reports } from './data/demo'
import type { AnalysisReport, AppTab, ManualRecordInput, WorkoutRecord } from './types/domain'

function App() {
  const location = useLocation()
  const navigate = useNavigate()
  const [toast, setToast] = useState('')
  const [workouts, setWorkouts] = useState<WorkoutRecord[]>(loadLocalWorkouts)
  const [localReports, setLocalReports] = useState<AnalysisReport[]>(loadLocalReports)
  const toastTimer = useRef<number | null>(null)
  const allReports = useMemo(() => [...localReports, ...reports], [localReports])

  useEffect(() => {
    getAnalysisReports().then((stored) => {
      setLocalReports(stored)
      persistLocalReports(stored)
    }).catch(() => undefined)
  }, [])

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

  const updateReportRecord = async (report: AnalysisReport, input: { displayName: string; trainingDate: string }) => {
    const updated = await updateAnalysisReport(report.id, input)
    setLocalReports((current) => {
      const next = current.map((item) => item.id === updated.id ? updated : item)
      persistLocalReports(next)
      return next
    })
    showToast('报告信息已更新')
  }

  const deleteReportRecord = async (report: AnalysisReport) => {
    await deleteAnalysisReport(report.id)
    setLocalReports((current) => {
      const next = current.filter((item) => item.id !== report.id)
      persistLocalReports(next)
      return next
    })
    showToast('报告及相关证据已删除')
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
          <Route path="/reports" element={<ReportsView allReports={allReports} onOpenReport={openReport} onUpdateReport={updateReportRecord} onDeleteReport={deleteReportRecord} onBack={() => navigate('/progress')} />} />
          <Route path="/reports/:reportId" element={<ReportRoute allReports={allReports} onLoaded={saveReport} onBack={() => navigate('/reports')} onToast={showToast} onReanalyze={(report) => { showToast('已为你打开分析页，请重新上传同一段视频'); navigate(`/analyze?sport=${report.sport}`) }} />} />
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

function ReportRoute({ allReports, onLoaded, onBack, onToast, onReanalyze }: { allReports: AnalysisReport[]; onLoaded: (report: AnalysisReport) => void; onBack: () => void; onToast: (message: string) => void; onReanalyze: (report: AnalysisReport) => void }) {
  const { reportId } = useParams()
  const cached = allReports.find((item) => item.id === reportId)
  const [report, setReport] = useState<AnalysisReport | null>(cached ?? null)
  const [failed, setFailed] = useState(false)
  const fetchedRef = useRef(false)

  useEffect(() => {
    if (!reportId || cached?.source === 'demo' || fetchedRef.current) return
    fetchedRef.current = true
    getAnalysisReport(reportId).then((loaded) => {
      setReport(loaded)
      onLoaded(loaded)
    }).catch(() => { if (!cached) setFailed(true) })
  }, [cached, onLoaded, reportId])

  if (report) return <ReportDetail report={report} onBack={onBack} onToast={onToast} onReanalyze={onReanalyze} />
  if (failed) return <Navigate to="/reports" replace />
  return <main className="route-loading"><span className="scan-line" /><p>正在加载动作报告</p></main>
}

export default App
