export type Sport = 'running' | 'swimming'

export type AppTab = 'home' | 'analyze' | 'progress' | 'profile'

export interface Metric {
  label: string
  value: string
  unit?: string
  delta: string
  tone: 'positive' | 'warning' | 'neutral'
}

export interface MetricTrend {
  key: string
  label: string
  unit: string
  previous: number
  current: number
  delta: number
  direction: 'improved' | 'regressed' | 'stable' | 'changed'
}

export interface Insight {
  id: string
  title: string
  summary: string
  impact?: string
  action: string
  successCue?: string
  severity: 'focus' | 'good' | 'observe'
  timestamp: string
  marker: string
  image?: string
  clip?: string
  clipStartSeconds?: number
}

export interface AnalysisReport {
  id: string
  source: 'demo' | 'video'
  sport: Sport
  title: string
  date: string
  displayName?: string
  createdAt?: string
  trainingDate?: string
  sourceHash?: string
  duration: string
  score: number
  headline: string
  summary: string
  image: string
  confidence?: number
  quality?: string
  swimStroke?: {
    stroke: 'freestyle' | 'breaststroke' | 'backstroke' | 'butterfly' | 'unknown'
    strokeName: string
    confidence: number
    candidates: Array<{ stroke: string; name: string; score: number }>
    correctedByUser?: boolean
    reusedFromSameVideo?: boolean
  }
  adviceNeedsReanalysis?: boolean
  qualityAssessment?: {
    status: 'pass' | 'limited'
    quality: string
    checks: { singlePerson: boolean; fullBodyCoverage: number; cameraStability: string; visibleCycles: number; view: string }
    blockingIssues: string[]
    suggestions: string[]
  }
  cycles?: Array<{ id: string; start: number; end: number; duration: number; confidence: number }>
  prescription?: { priorityIssueId: string; reason: string; drill: string; volume: string; rest: string; focusCue: string; successCue: string }
  pipeline?: { pipelineVersion: string; poseModelVersion: string; ruleVersion: string; promptVersion: string }
  modelReview?: { status: 'reviewed' | 'engineering_fallback'; reason: string; evidenceValidated: boolean }
  comparison?: { status: 'comparable' | 'not_comparable'; previousReportId?: string; previousDate?: string; improved?: string[]; remaining?: string[]; newIssues?: string[]; metricTrends?: MetricTrend[]; basis?: string; reason?: string }
  keyMeasurements?: Record<string, { value: number; unit: string; label: string; betterWhen: 'lower' | 'higher' | 'range'; target?: number }>
  fileName?: string
  metadata?: {
    fps: number
    frameCount: number
    width: number
    height: number
    durationSeconds: number
    sampledFrames: number
    sampleRateFps?: number
    analysisSeconds?: number
    inferenceMaxSide?: number
    analysisWorkers?: number
    maxSampleFrames?: number
    bodyAxisAngleFromHorizontal?: number
    swimStrokeConfidence?: number
    detectedFrames: number
    detectionRatio: number
    confidence: number
  }
  metrics: Metric[]
  insights: Insight[]
}

export interface WorkoutRecord {
  id: string
  sport: Sport
  date: string
  distance: string
  duration: string
  source: 'manual' | 'device' | 'video'
}

export interface DataSource {
  id: string
  name: string
  status: 'native_required' | 'web_oauth' | 'planned'
  detail: string
}

export interface ManualRecordInput {
  sport: Sport
  distance: number
  minutes: number
  seconds: number
  date: string
}
