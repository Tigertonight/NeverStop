import { describe, it, expect, beforeEach } from 'vitest'
import { loadReportFeedback, persistInsightFeedback } from './feedback-storage'

describe('feedback-storage', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  it('returns empty object when nothing stored', () => {
    expect(loadReportFeedback('r1')).toEqual({})
  })

  it('persists and reloads feedback for a report', () => {
    persistInsightFeedback('r1', 'i1', 'accurate')
    persistInsightFeedback('r1', 'i2', 'unclear')
    expect(loadReportFeedback('r1')).toEqual({ i1: 'accurate', i2: 'unclear' })
  })

  it('scopes feedback per report', () => {
    persistInsightFeedback('r1', 'i1', 'accurate')
    persistInsightFeedback('r2', 'i1', 'inaccurate')
    expect(loadReportFeedback('r1')).toEqual({ i1: 'accurate' })
    expect(loadReportFeedback('r2')).toEqual({ i1: 'inaccurate' })
  })

  it('overwrites an existing value for the same insight', () => {
    persistInsightFeedback('r1', 'i1', 'accurate')
    persistInsightFeedback('r1', 'i1', 'inaccurate')
    expect(loadReportFeedback('r1')).toEqual({ i1: 'inaccurate' })
  })

  it('ignores corrupt storage payloads', () => {
    window.localStorage.setItem('neverstop.insight-feedback.v1', 'not-json')
    expect(loadReportFeedback('r1')).toEqual({})
  })
})
