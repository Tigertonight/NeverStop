import { useState, type ReactNode } from 'react'
import {
  AlertTriangle,
  ArrowLeft,
  Check,
  Footprints,
  Info,
  Pencil,
  Trash2,
  Waves,
} from 'lucide-react'
import { navItems } from './nav'
import { useModalDismiss } from '../hooks/useModalDismiss'
import { defaultReportName, formatReportDate, formatWorkoutDate } from '../lib/format'
import type { AnalysisReport, AppTab, Insight, Sport, WorkoutRecord } from '../types/domain'

/**
 * 应用内一致的确认弹窗，替代原生 window.confirm。
 * onConfirm 可返回 Promise：进行中禁用按钮、失败时展示行内错误。
 */
export function ConfirmDialog({ title, description, confirmLabel = '确认', cancelLabel = '取消', tone = 'danger', onConfirm, onCancel }: {
  title: string
  description?: ReactNode
  confirmLabel?: string
  cancelLabel?: string
  tone?: 'danger' | 'primary'
  onConfirm: () => void | Promise<void>
  onCancel: () => void
}) {
  const dialogRef = useModalDismiss<HTMLDivElement>(onCancel)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const confirm = async () => {
    setBusy(true)
    try {
      await onConfirm()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '操作失败，请重试。')
      setBusy(false)
    }
  }
  return (
    <div className="modal-backdrop confirm-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) onCancel() }}>
      <div ref={dialogRef} className="confirm-sheet" role="alertdialog" aria-modal="true" aria-labelledby="confirm-title" aria-describedby={description ? 'confirm-desc' : undefined} tabIndex={-1}>
        <div className={`confirm-icon ${tone}`}><AlertTriangle size={22} /></div>
        <h2 id="confirm-title">{title}</h2>
        {description ? <p id="confirm-desc" className="confirm-desc">{description}</p> : null}
        {error ? <div className="form-error standalone" role="alert">{error}</div> : null}
        <div className="confirm-actions">
          <button className="secondary-button wide" type="button" disabled={busy} onClick={onCancel}>{cancelLabel}</button>
          <button className={`${tone === 'danger' ? 'danger-button' : 'primary-button'} wide`} type="button" disabled={busy} onClick={confirm}>{busy ? '处理中…' : confirmLabel}</button>
        </div>
      </div>
    </div>
  )
}

export function SportIcon({ sport, size = 18 }: { sport: Sport; size?: number }) {
  return sport === 'running' ? <Footprints size={size} /> : <Waves size={size} />
}

export function Brand() {
  return (
    <div className="brand" aria-label="NeverStop">
      <span className="brand-mark"><span /></span>
      <span className="brand-name">NeverStop</span>
    </div>
  )
}

export function TopBar({ title, action, onBack }: { title?: string; action?: ReactNode; onBack?: () => void }) {
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

export function BottomNav({ active, onChange }: { active: AppTab; onChange: (tab: AppTab) => void }) {
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

export function SideNav({ active, onChange }: { active: AppTab; onChange: (tab: AppTab) => void }) {
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

export function DemoNotice({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`demo-notice ${compact ? 'compact' : ''}`}>
      <Info size={16} />
      <div><strong>当前为交互演示</strong><span>结果来自示例数据，不代表对上传视频的真实判断。</span></div>
    </div>
  )
}

export function ScoreRing({ score, compact = false, isDemo = true }: { score: number; compact?: boolean; isDemo?: boolean }) {
  return (
    <div className={`score-ring ${compact ? 'compact' : ''}`} style={{ '--score-deg': `${score * 3.6}deg` } as React.CSSProperties}>
      <div><strong>{score}</strong><span>{isDemo ? '示例分' : '动作分'}</span></div>
    </div>
  )
}

export function EvidenceOverlay({ sport, insight }: { sport: Sport; insight?: Insight }) {
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

export function ReportPreview({ report, onOpen, onEdit, onDelete }: { report: AnalysisReport; onOpen: () => void; onEdit?: () => void; onDelete?: () => void }) {
  const isDemo = report.source === 'demo'
  return (
    <article className="report-preview">
      <div className="report-thumb-shell">
        <button className="report-image-open" onClick={onOpen} aria-label={`查看${defaultReportName(report)}`}>
          <div className="report-thumb">
          <img src={report.image} alt={`${report.sport === 'running' ? '跑步' : '游泳'}${isDemo ? '示例' : '视频'}证据帧`} />
          {isDemo ? <EvidenceOverlay sport={report.sport} insight={report.insights[0]} /> : null}
          <span className={`sport-badge ${report.sport}`}><SportIcon sport={report.sport} size={14} />{report.sport === 'running' ? '跑步' : report.swimStroke?.strokeName ?? '游泳'}</span>
          <span className={`media-demo-label ${isDemo ? '' : 'real'}`}>{isDemo ? '示例' : '真实视频'}</span>
          </div>
        </button>
        {!isDemo && onEdit && onDelete ? <span className="report-actions overlay"><button onClick={onEdit} aria-label="编辑报告" title="编辑报告"><Pencil size={16} /></button><button onClick={onDelete} aria-label="删除报告" title="删除报告"><Trash2 size={16} /></button></span> : null}
      </div>
      <button className="report-open" onClick={onOpen} aria-label={`查看${defaultReportName(report)}详情`}>
        <div className="report-preview-body">
          <div><span className="eyebrow">{isDemo ? '示例报告' : formatReportDate(report)}</span><h3>{isDemo ? report.title : defaultReportName(report)}</h3>{!isDemo ? <p>{report.headline}</p> : null}</div>
          <div className="report-score"><strong>{isDemo ? report.score : report.insights.length}</strong><span>{isDemo ? '示例分' : '个关键时刻'}</span></div>
        </div>
      </button>
    </article>
  )
}

export function SectionHeading({ title, action }: { title: string; action?: ReactNode }) {
  return <div className="section-heading"><h2>{title}</h2>{action}</div>
}

export function SportSelector({ value, onChange }: { value: Sport; onChange: (sport: Sport) => void }) {
  return (
    <div className="segmented" role="tablist" aria-label="运动类型">
      <button className={value === 'running' ? 'active' : ''} onClick={() => onChange('running')} role="tab" aria-selected={value === 'running'}><Footprints size={17} /> 跑步</button>
      <button className={value === 'swimming' ? 'active' : ''} onClick={() => onChange('swimming')} role="tab" aria-selected={value === 'swimming'}><Waves size={17} /> 游泳</button>
    </div>
  )
}

export function WorkoutRow({ workout }: { workout: WorkoutRecord }) {
  return <div className="workout-row"><span className={`workout-icon ${workout.sport}`}><SportIcon sport={workout.sport} /></span><div><strong>{workout.distance}</strong><p>{formatWorkoutDate(workout.date)} · {workout.duration}</p></div><span className="source-label">{workout.source === 'manual' ? '本机' : workout.source === 'device' ? '设备' : '视频'}</span></div>
}

export function Toast({ message }: { message: string }) {
  return <div className="toast" role="status"><Check size={16} />{message}</div>
}
