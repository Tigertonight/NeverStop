import type { AnalysisReport } from '../types/domain'

export function getGreeting() {
  const hour = new Date().getHours()
  if (hour < 6) return '夜深了'
  if (hour < 12) return '上午好'
  if (hour < 18) return '下午好'
  return '晚上好'
}

export function todayValue() {
  const date = new Date()
  const offset = date.getTimezoneOffset() * 60_000
  return new Date(date.getTime() - offset).toISOString().slice(0, 10)
}

export function formatWorkoutDate(value: string) {
  if (value === todayValue() || value === '今天') return '今天'
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
  return match ? `${Number(match[2])}月${Number(match[3])}日` : value
}

export function formatReportDate(report: AnalysisReport) {
  const source = report.createdAt ? new Date(report.createdAt) : report.trainingDate ? new Date(`${report.trainingDate}T00:00:00`) : null
  if (!source || Number.isNaN(source.getTime())) return report.date
  const date = `${source.getFullYear()}年${source.getMonth() + 1}月${source.getDate()}日`
  return report.createdAt ? `${date} ${source.getHours().toString().padStart(2, '0')}:${source.getMinutes().toString().padStart(2, '0')}` : date
}

export function defaultReportName(report: AnalysisReport) {
  if (report.displayName) return report.displayName
  const value = report.trainingDate ?? report.createdAt?.slice(0, 10)
  const match = value ? /^(\d{4})-(\d{2})-(\d{2})$/.exec(value) : null
  return match ? `${Number(match[2])}月${Number(match[3])}日训练记录` : report.title
}

/** 用于报告列表分组/排序的日期键（YYYY-MM-DD），示例报告归入空键。 */
function reportDateKey(report: AnalysisReport): string {
  if (report.trainingDate) return report.trainingDate
  if (report.createdAt) return report.createdAt.slice(0, 10)
  return ''
}

/** 把日期键渲染成分组标题：今天 / 昨天 / X月X日 / 示例报告。 */
export function formatReportGroupLabel(key: string): string {
  if (!key) return '示例报告'
  const today = todayValue()
  if (key === today) return '今天'
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(key)
  if (!match) return key
  const yesterday = new Date()
  yesterday.setDate(yesterday.getDate() - 1)
  const offset = yesterday.getTimezoneOffset() * 60_000
  if (key === new Date(yesterday.getTime() - offset).toISOString().slice(0, 10)) return '昨天'
  const now = new Date()
  const prefix = Number(match[1]) === now.getFullYear() ? '' : `${match[1]}年`
  return `${prefix}${Number(match[2])}月${Number(match[3])}日`
}

/**
 * 按日期把报告分组（新→旧），示例报告（无日期）排在最后。
 * 返回 [{ key, label, reports }]。
 */
export function groupReportsByDate(reports: AnalysisReport[]): Array<{ key: string; label: string; reports: AnalysisReport[] }> {
  const buckets = new Map<string, AnalysisReport[]>()
  for (const report of reports) {
    const key = reportDateKey(report)
    const bucket = buckets.get(key)
    if (bucket) bucket.push(report)
    else buckets.set(key, [report])
  }
  return Array.from(buckets.keys())
    .sort((a, b) => {
      if (a === b) return 0
      if (!a) return 1
      if (!b) return -1
      return a < b ? 1 : -1
    })
    .map((key) => ({ key, label: formatReportGroupLabel(key), reports: buckets.get(key)! }))
}

/** 报告是否匹配搜索词（名称 / 标题 / 结论 / 泳姿名）。 */
export function reportMatchesQuery(report: AnalysisReport, query: string): boolean {
  const trimmed = query.trim().toLowerCase()
  if (!trimmed) return true
  const haystack = [
    defaultReportName(report),
    report.title,
    report.headline,
    report.swimStroke?.strokeName ?? '',
  ].join(' ').toLowerCase()
  return haystack.includes(trimmed)
}
