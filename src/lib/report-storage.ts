import type { AnalysisReport } from '../types/domain'

const STORAGE_KEY = 'neverstop.analysis-reports.v1'

export function loadLocalReports(): AnalysisReport[] {
  try {
    const value = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '[]')
    return Array.isArray(value) ? value.filter((item) => item?.source === 'video') : []
  } catch {
    return []
  }
}

export function persistLocalReports(reports: AnalysisReport[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(reports.slice(0, 20)))
}
