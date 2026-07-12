import { describe, it, expect, vi, afterEach } from 'vitest'
import { defaultReportName, formatReportDate, formatWorkoutDate, getGreeting, todayValue } from './format'
import type { AnalysisReport } from '../types/domain'

function makeReport(partial: Partial<AnalysisReport>): AnalysisReport {
  return {
    id: 'r1',
    sport: 'running',
    date: '占位日期',
    title: '默认标题',
    score: 80,
    headline: '',
    summary: '',
    duration: '',
    image: '',
    source: 'video',
    metrics: [],
    insights: [],
    ...partial,
  } as AnalysisReport
}

describe('todayValue', () => {
  it('returns an ISO yyyy-mm-dd string', () => {
    expect(todayValue()).toMatch(/^\d{4}-\d{2}-\d{2}$/)
  })
})

describe('formatWorkoutDate', () => {
  it('maps today to 今天', () => {
    expect(formatWorkoutDate(todayValue())).toBe('今天')
    expect(formatWorkoutDate('今天')).toBe('今天')
  })

  it('formats a full date into 月日', () => {
    expect(formatWorkoutDate('2026-03-09')).toBe('3月9日')
  })

  it('passes through unrecognized values', () => {
    expect(formatWorkoutDate('unknown')).toBe('unknown')
  })
})

describe('getGreeting', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it.each([
    [3, '夜深了'],
    [9, '上午好'],
    [14, '下午好'],
    [21, '晚上好'],
  ])('at hour %i returns %s', (hour, expected) => {
    vi.useFakeTimers()
    const date = new Date()
    date.setHours(hour, 0, 0, 0)
    vi.setSystemTime(date)
    expect(getGreeting()).toBe(expected)
  })
})

describe('formatReportDate', () => {
  it('falls back to report.date when no timestamps', () => {
    expect(formatReportDate(makeReport({ date: '占位日期' }))).toBe('占位日期')
  })

  it('formats trainingDate as 年月日 without time', () => {
    expect(formatReportDate(makeReport({ trainingDate: '2026-03-09' }))).toBe('2026年3月9日')
  })

  it('formats createdAt with time', () => {
    const result = formatReportDate(makeReport({ createdAt: '2026-03-09T08:05:00' }))
    expect(result).toMatch(/^2026年3月9日 \d{2}:\d{2}$/)
  })
})

describe('defaultReportName', () => {
  it('prefers displayName', () => {
    expect(defaultReportName(makeReport({ displayName: '我的晨跑' }))).toBe('我的晨跑')
  })

  it('derives a name from trainingDate', () => {
    expect(defaultReportName(makeReport({ trainingDate: '2026-03-09' }))).toBe('3月9日训练记录')
  })

  it('falls back to title', () => {
    expect(defaultReportName(makeReport({ title: '跑步分析' }))).toBe('跑步分析')
  })
})
