import type { AnalysisReport, Sport, WorkoutRecord } from '../types/domain'

export interface AnalysisJob {
  id: string
  sport: Sport
  status: 'queued' | 'preprocessing' | 'estimating_pose' | 'building_report' | 'completed' | 'failed'
  progress: number
  stage?: string
  reportId?: string
  errorCode?: string
  errorMessage?: string
}

export interface VideoAnalysisGateway {
  createJob(input: { sport: Sport; video: File }): Promise<AnalysisJob>
  getJob(jobId: string): Promise<AnalysisJob>
  getReport(reportId: string): Promise<AnalysisReport>
}

export interface WorkoutImportPayload {
  provider: 'apple_health' | 'garmin' | 'health_connect' | 'keep' | 'file'
  externalId: string
  sport: Sport
  startedAt: string
  durationSeconds: number
  distanceMeters?: number
  samples?: {
    heartRate?: Array<{ offsetSeconds: number; bpm: number }>
    pace?: Array<{ offsetSeconds: number; secondsPerKm: number }>
    cadence?: Array<{ offsetSeconds: number; stepsPerMinute: number }>
    gps?: Array<{ offsetSeconds: number; lat: number; lng: number; altitudeMeters?: number }>
  }
  rawFileRef?: string
}

export interface WorkoutRepository {
  list(): Promise<WorkoutRecord[]>
  saveManual(record: Omit<WorkoutRecord, 'id' | 'source'>): Promise<WorkoutRecord>
  import(payload: WorkoutImportPayload): Promise<WorkoutRecord>
}
