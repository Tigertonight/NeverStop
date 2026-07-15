import { describe, it, expect, vi, afterEach } from 'vitest'
import { defaultReportName, formatReportDate, formatReportGroupLabel, formatWorkoutDate, getGreeting, groupReportsByDate, reportMatchesQuery, todayValue } from './format'
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

describe('formatReportGroupLabel', () => {
  afterEach(() => vi.useRealTimers())

  it('labels empty key as 示例报告', () => {
    expect(formatReportGroupLabel('')).toBe('示例报告')
  })

  it('labels today and yesterday', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-03-09T10:00:00'))
    expect(formatReportGroupLabel('2026-03-09')).toBe('今天')
    expect(formatReportGroupLabel('2026-03-08')).toBe('昨天')
  })

  it('drops year for same-year dates', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-03-09T10:00:00'))
    expect(formatReportGroupLabel('2026-01-02')).toBe('1月2日')
    expect(formatReportGroupLabel('2025-12-31')).toBe('2025年12月31日')
  })
})

describe('groupReportsByDate', () => {
  it('groups by date, newest first, demo (no date) last', () => {
    const groups = groupReportsByDate([
      makeReport({ id: 'a', trainingDate: '2026-03-01' }),
      makeReport({ id: 'demo', source: 'demo' }),
      makeReport({ id: 'b', trainingDate: '2026-03-05' }),
      makeReport({ id: 'c', trainingDate: '2026-03-05' }),
    ])
    expect(groups.map((g) => g.key)).toEqual(['2026-03-05', '2026-03-01', ''])
    expect(groups[0].reports.map((r) => r.id)).toEqual(['b', 'c'])
    expect(groups[2].reports.map((r) => r.id)).toEqual(['demo'])
  })

  it('uses createdAt date when trainingDate missing', () => {
    const groups = groupReportsByDate([makeReport({ id: 'x', createdAt: '2026-03-09T08:00:00' })])
    expect(groups[0].key).toBe('2026-03-09')
  })
})

describe('reportMatchesQuery', () => {
  const report = makeReport({ displayName: '周一晨泳', headline: '入水点越过中线', swimStroke: { stroke: 'freestyle', strokeName: '自由泳', confidence: 90, candidates: [] } })

  it('matches empty query', () => {
    expect(reportMatchesQuery(report, '')).toBe(true)
    expect(reportMatchesQuery(report, '   ')).toBe(true)
  })

  it('matches on name, headline and stroke name, case-insensitive', () => {
    expect(reportMatchesQuery(report, '晨泳')).toBe(true)
    expect(reportMatchesQuery(report, '中线')).toBe(true)
    expect(reportMatchesQuery(report, '自由泳')).toBe(true)
  })

  it('returns false when nothing matches', () => {
    expect(reportMatchesQuery(report, '蝶泳')).toBe(false)
  })
})
