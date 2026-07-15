export type FeedbackValue = 'accurate' | 'inaccurate' | 'unclear'

const STORAGE_KEY = 'neverstop.insight-feedback.v1'

interface StoredFeedback {
  version: 1
  /** key = `${reportId}:${insightId}` -> 反馈值 */
  entries: Record<string, FeedbackValue>
}

function feedbackKey(reportId: string, insightId: string): string {
  return `${reportId}:${insightId}`
}

function readAll(): Record<string, FeedbackValue> {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw) as StoredFeedback
    return parsed.version === 1 && parsed.entries ? parsed.entries : {}
  } catch {
    return {}
  }
}

/** 读取某报告下所有已提交反馈：{ insightId -> value }。 */
export function loadReportFeedback(reportId: string): Record<string, FeedbackValue> {
  const prefix = `${reportId}:`
  const all = readAll()
  const result: Record<string, FeedbackValue> = {}
  for (const [key, value] of Object.entries(all)) {
    if (key.startsWith(prefix)) result[key.slice(prefix.length)] = value
  }
  return result
}

/** 记录一条反馈（刷新后仍可回显）。 */
export function persistInsightFeedback(reportId: string, insightId: string, value: FeedbackValue): void {
  const all = readAll()
  all[feedbackKey(reportId, insightId)] = value
  const payload: StoredFeedback = { version: 1, entries: all }
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(payload))
  } catch {
    // localStorage 不可用时静默降级：本次会话内的 state 仍然有效
  }
}
