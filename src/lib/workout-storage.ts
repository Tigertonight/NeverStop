import type { WorkoutRecord } from '../types/domain'

const STORAGE_KEY = 'neverstop.workouts.v1'

interface StoredWorkouts {
  version: 1
  records: WorkoutRecord[]
}

export function loadLocalWorkouts(): WorkoutRecord[] {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as StoredWorkouts
    return parsed.version === 1 && Array.isArray(parsed.records) ? parsed.records : []
  } catch {
    return []
  }
}

export function persistLocalWorkouts(records: WorkoutRecord[]) {
  const payload: StoredWorkouts = { version: 1, records }
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(payload))
}
