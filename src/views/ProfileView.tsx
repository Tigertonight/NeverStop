import { useState, type FormEvent } from 'react'
import { Activity, BarChart3, ChevronRight, Link2, LockKeyhole, Plus, ShieldCheck, Upload, X } from 'lucide-react'
import { SectionHeading, TopBar, WorkoutRow } from '../components/ui'
import { useModalDismiss } from '../hooks/useModalDismiss'
import { todayValue } from '../lib/format'
import { dataSources } from '../data/demo'
import { getFeedbackStats, type FeedbackStats } from '../lib/analysis-api'
import type { ManualRecordInput, Sport, WorkoutRecord } from '../types/domain'

function ManualRecordModal({ onClose, onSave }: { onClose: () => void; onSave: (input: ManualRecordInput) => void }) {
  const dialogRef = useModalDismiss<HTMLFormElement>(onClose)
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
      <form ref={dialogRef} className="modal-sheet" role="dialog" aria-modal="true" aria-labelledby="manual-title" onSubmit={submit}>
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

export function ProfileView({ workouts, onSaveWorkout, onToast }: { workouts: WorkoutRecord[]; onSaveWorkout: (input: ManualRecordInput) => void; onToast: (message: string) => void }) {
  const [showManual, setShowManual] = useState(false)
  const [stats, setStats] = useState<FeedbackStats | null>(null)
  const [loadingStats, setLoadingStats] = useState(false)
  const sourceLabel = { native_required: '需 App', web_oauth: '可规划', planned: '规划中' } as const

  const loadStats = async () => {
    setLoadingStats(true)
    try {
      setStats(await getFeedbackStats())
    } catch (error) {
      onToast(error instanceof Error ? error.message : '暂时无法读取反馈统计')
    } finally {
      setLoadingStats(false)
    }
  }

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
        <section className="feedback-diagnostics"><SectionHeading title="建议反馈诊断" action={<span className="section-note">用于调参</span>} />
          {stats === null ? (
            <button className="secondary-button compact" onClick={loadStats} disabled={loadingStats}><BarChart3 size={16} /> {loadingStats ? '加载中…' : '查看反馈统计'}</button>
          ) : stats.total === 0 ? (
            <p className="section-note">还没有收到任何建议反馈。用户在报告里标注「准确/不准确」后，这里会汇总各类建议的不满意率，帮助定位需要复查的规则。</p>
          ) : (
            <div className="diagnostics-body">
              <p className="section-note">共 {stats.total} 条反馈 · 整体不满意率 {(stats.overallInaccurateRate * 100).toFixed(0)}%（按不满意率排序，越高越需复查）</p>
              <ul className="diagnostics-list">
                {stats.byInsight.map((row) => (
                  <li key={row.insightId} className={row.inaccurateRate >= 0.5 ? 'flag' : ''}>
                    <span className="diagnostics-id">{row.insightId}</span>
                    <span className="diagnostics-bar"><i style={{ width: `${row.inaccurateRate * 100}%` }} /></span>
                    <span className="diagnostics-rate">{(row.inaccurateRate * 100).toFixed(0)}%<small> · {row.total} 条</small></span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      </main>
      {showManual ? <ManualRecordModal onClose={() => setShowManual(false)} onSave={(input) => { onSaveWorkout(input); setShowManual(false) }} /> : null}
    </div>
  )
}
