import { useMemo, useState, type FormEvent } from 'react'
import { Check, Footprints, Search, Trash2, Waves, X } from 'lucide-react'
import { ConfirmDialog, ReportPreview, TopBar } from '../components/ui'
import { useModalDismiss } from '../hooks/useModalDismiss'
import { defaultReportName, groupReportsByDate, reportMatchesQuery, todayValue } from '../lib/format'
import type { AnalysisReport, Sport } from '../types/domain'

function ReportEditModal({ report, onClose, onSave, onDelete }: { report: AnalysisReport; onClose: () => void; onSave: (input: { displayName: string; trainingDate: string }) => Promise<void>; onDelete: () => Promise<void> }) {
  const dialogRef = useModalDismiss<HTMLFormElement>(onClose)
  const [displayName, setDisplayName] = useState(defaultReportName(report))
  const [trainingDate, setTrainingDate] = useState(report.trainingDate ?? report.createdAt?.slice(0, 10) ?? todayValue())
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!displayName.trim()) return setError('请输入报告名称。')
    setBusy(true)
    try { await onSave({ displayName: displayName.trim(), trainingDate }); onClose() } catch (reason) { setError(reason instanceof Error ? reason.message : '保存失败') } finally { setBusy(false) }
  }
  return (
    <>
      <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}><form ref={dialogRef} className="modal-sheet" role="dialog" aria-modal="true" aria-labelledby="report-edit-title" onSubmit={submit}><div className="modal-head"><h2 id="report-edit-title">编辑动作报告</h2><button className="icon-button quiet" type="button" onClick={onClose} aria-label="关闭"><X size={20} /></button></div><label><span>报告名称</span><input value={displayName} maxLength={80} onChange={(event) => setDisplayName(event.target.value)} /></label><label><span>训练日期</span><input type="date" value={trainingDate} onChange={(event) => setTrainingDate(event.target.value)} /></label>{error ? <div className="form-error standalone">{error}</div> : null}<button className="primary-button wide" disabled={busy} type="submit"><Check size={17} />保存修改</button><button className="danger-button wide" disabled={busy} type="button" onClick={() => setConfirmingDelete(true)}><Trash2 size={17} />删除报告</button></form></div>
      {confirmingDelete ? (
        <ConfirmDialog
          title={`确定删除“${displayName}”？`}
          description="相关证据图片和短片也会一并删除，且无法恢复。"
          confirmLabel="删除报告"
          cancelLabel="保留"
          onCancel={() => setConfirmingDelete(false)}
          onConfirm={async () => { await onDelete(); onClose() }}
        />
      ) : null}
    </>
  )
}

export function ReportsView({ allReports, onOpenReport, onUpdateReport, onDeleteReport, onBack }: { allReports: AnalysisReport[]; onOpenReport: (report: AnalysisReport) => void; onUpdateReport: (report: AnalysisReport, input: { displayName: string; trainingDate: string }) => Promise<void>; onDeleteReport: (report: AnalysisReport) => Promise<void>; onBack: () => void }) {
  const [sport, setSport] = useState<'all' | Sport>('all')
  const [query, setQuery] = useState('')
  const [editing, setEditing] = useState<AnalysisReport | null>(null)
  const visibleReports = useMemo(
    () => allReports.filter((report) => (sport === 'all' || report.sport === sport) && reportMatchesQuery(report, query)),
    [sport, query, allReports],
  )
  const groups = useMemo(() => groupReportsByDate(visibleReports), [visibleReports])
  return (
    <div className="view reports-view">
      <TopBar title="动作报告" onBack={onBack} />
      <main>
        <div className="report-search">
          <Search size={17} />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索报告名称、结论或泳姿" aria-label="搜索报告" />
          {query ? <button type="button" className="icon-button quiet" onClick={() => setQuery('')} aria-label="清除搜索"><X size={16} /></button> : null}
        </div>
        <div className="filter-chips">
          <button className={sport === 'all' ? 'active' : ''} onClick={() => setSport('all')}>全部</button>
          <button className={sport === 'running' ? 'active' : ''} onClick={() => setSport('running')}><Footprints size={15} />跑步</button>
          <button className={sport === 'swimming' ? 'active' : ''} onClick={() => setSport('swimming')}><Waves size={15} />游泳</button>
        </div>
        {groups.length === 0 ? (
          <div className="empty-state"><span><Search size={22} /></span><div><strong>没有匹配的报告</strong><p>{query ? '换个关键词，或清除搜索条件试试。' : '还没有该类别的报告。'}</p></div></div>
        ) : (
          groups.map((group) => (
            <section className="report-group" key={group.key || 'demo'}>
              <h2 className="report-group-title">{group.label}<span>{group.reports.length}</span></h2>
              <div className="report-list">
                {group.reports.map((report) => <ReportPreview key={report.id} report={report} onOpen={() => onOpenReport(report)} onEdit={report.source === 'video' ? () => setEditing(report) : undefined} onDelete={report.source === 'video' ? () => setEditing(report) : undefined} />)}
              </div>
            </section>
          ))
        )}
      </main>
      {editing ? <ReportEditModal report={editing} onClose={() => setEditing(null)} onSave={(input) => onUpdateReport(editing, input)} onDelete={() => onDeleteReport(editing)} /> : null}
    </div>
  )
}
