import type { AnalysisJob } from './contracts'
import type { AnalysisReport, Sport } from '../types/domain'

const API_BASE = (import.meta.env.VITE_ANALYSIS_API_URL ?? 'http://127.0.0.1:8000').replace(/\/$/, '')

export class AnalysisApiError extends Error {
  constructor(message: string, public status?: number) {
    super(message)
    this.name = 'AnalysisApiError'
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, init)
  } catch {
    throw new AnalysisApiError('无法连接本地分析服务，请确认服务已经启动。')
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null
    throw new AnalysisApiError(body?.detail ?? '分析服务请求失败，请稍后重试。', response.status)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export function createAnalysisJob(video: File, sport: Sport) {
  const body = new FormData()
  body.append('sport', sport)
  body.append('video', video)
  return request<AnalysisJob>('/api/analysis/jobs', { method: 'POST', body })
}

export function getAnalysisJob(jobId: string) {
  return request<AnalysisJob>(`/api/analysis/jobs/${jobId}`)
}

export function getAnalysisReport(reportId: string) {
  return request<AnalysisReport>(`/api/reports/${reportId}`)
}

export function getAnalysisReports() {
  return request<AnalysisReport[]>('/api/reports')
}

export function correctSwimStroke(reportId: string, stroke: 'freestyle' | 'breaststroke' | 'backstroke' | 'butterfly') {
  return request<AnalysisReport>(`/api/reports/${reportId}/stroke`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ stroke }) })
}

export function submitInsightFeedback(reportId: string, insightId: string, value: 'accurate' | 'inaccurate' | 'unclear' | 'not_visible' | 'not_suitable') {
  return request<{ id: string }>(`/api/reports/${reportId}/feedback`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ insightId, value }) })
}

export function updateAnalysisReport(reportId: string, input: { displayName: string; trainingDate: string }) {
  return request<AnalysisReport>(`/api/reports/${reportId}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input) })
}

export async function deleteAnalysisReport(reportId: string) {
  await request<{ deleted: boolean }>(`/api/reports/${reportId}`, { method: 'DELETE' })
}
