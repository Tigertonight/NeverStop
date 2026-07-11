export type Sport = 'running' | 'swimming'

export type AppTab = 'home' | 'analyze' | 'progress' | 'profile'

export interface Metric {
  label: string
  value: string
  unit?: string
  delta: string
  tone: 'positive' | 'warning' | 'neutral'
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
}

export interface AnalysisReport {
  id: string
  source: 'demo' | 'video'
  sport: Sport
  title: string
  date: string
  duration: string
  score: number
  headline: string
  summary: string
  image: string
  confidence?: number
  quality?: string
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
    bodyAxisAngleFromHorizontal?: number
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
