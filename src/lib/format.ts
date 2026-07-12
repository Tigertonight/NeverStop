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
