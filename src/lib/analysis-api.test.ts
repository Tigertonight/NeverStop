import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import {
  AnalysisApiError,
  analysisApiHost,
  correctSwimStroke,
  createAnalysisJob,
  deleteAnalysisReport,
  getAnalysisJob,
  getAnalysisReports,
  submitInsightFeedback,
  updateAnalysisReport,
} from './analysis-api'

describe('analysisApiHost', () => {
  it('returns host of the default local API base', () => {
    expect(analysisApiHost()).toBe('127.0.0.1:8000')
  })
})

describe('analysis-api request error mapping', () => {
  const originalFetch = globalThis.fetch

  afterEach(() => {
    globalThis.fetch = originalFetch
    vi.restoreAllMocks()
  })

  it('throws a friendly connection error when fetch rejects', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new TypeError('network down'))
    await expect(getAnalysisJob('abc')).rejects.toMatchObject({ name: 'AnalysisApiError' })
    await expect(getAnalysisJob('abc')).rejects.toThrow(/无法连接/)
  })

  it('surfaces the server detail message on non-ok responses', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 415,
      json: async () => ({ detail: '只支持 MP4 或 MOV 视频。' }),
    } as Response)
    const error = await getAnalysisJob('abc').catch((e) => e)
    expect(error).toBeInstanceOf(AnalysisApiError)
    expect(error.status).toBe(415)
    expect(error.message).toBe('只支持 MP4 或 MOV 视频。')
  })

  it('falls back to a generic message when body has no detail', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => { throw new Error('not json') },
    } as unknown as Response)
    await expect(getAnalysisJob('abc')).rejects.toThrow(/请求失败/)
  })

  it('returns parsed json on success', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ id: 'job-1', status: 'queued', progress: 5 }),
    } as Response)
    await expect(getAnalysisJob('job-1')).resolves.toMatchObject({ id: 'job-1' })
  })

  it('treats 204 as undefined without parsing body', async () => {
    const json = vi.fn()
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: true, status: 204, json } as unknown as Response)
    await expect(deleteAnalysisReport('r1')).resolves.toBeUndefined()
    expect(json).not.toHaveBeenCalled()
  })
})

describe('analysis-api request construction', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ([]),
    } as Response)
    globalThis.fetch = fetchMock as unknown as typeof fetch
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('fetches the reports collection', async () => {
    await getAnalysisReports()
    expect(fetchMock.mock.calls[0][0]).toMatch(/\/api\/reports$/)
  })

  it('issues a DELETE for deleteAnalysisReport', async () => {
    fetchMock.mockResolvedValueOnce({ ok: true, status: 204, json: async () => undefined } as unknown as Response)
    await deleteAnalysisReport('r1')
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toMatch(/\/api\/reports\/r1$/)
    expect(init).toMatchObject({ method: 'DELETE' })
  })

  it('PATCHes stroke correction with json body', async () => {
    fetchMock.mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ id: 'r1' }) } as Response)
    await correctSwimStroke('r1', 'breaststroke')
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toMatch(/\/api\/reports\/r1\/stroke$/)
    expect(init.method).toBe('PATCH')
    expect(JSON.parse(init.body as string)).toEqual({ stroke: 'breaststroke' })
  })

  it('POSTs insight feedback', async () => {
    fetchMock.mockResolvedValueOnce({ ok: true, status: 201, json: async () => ({ id: 'f1' }) } as Response)
    await submitInsightFeedback('r1', 'insight-2', 'inaccurate')
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toMatch(/\/api\/reports\/r1\/feedback$/)
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toEqual({ insightId: 'insight-2', value: 'inaccurate' })
  })

  it('PATCHes report metadata for updateAnalysisReport', async () => {
    fetchMock.mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ id: 'r1' }) } as Response)
    await updateAnalysisReport('r1', { displayName: '晨跑', trainingDate: '2026-03-09' })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toMatch(/\/api\/reports\/r1$/)
    expect(init.method).toBe('PATCH')
    expect(JSON.parse(init.body as string)).toEqual({ displayName: '晨跑', trainingDate: '2026-03-09' })
  })

  it('posts FormData with sport and video for createAnalysisJob', async () => {
    fetchMock.mockResolvedValueOnce({ ok: true, status: 202, json: async () => ({ id: 'j1' }) } as Response)
    const file = new File([new Uint8Array([1, 2, 3])], 'clip.mp4', { type: 'video/mp4' })
    await createAnalysisJob(file, 'swimming')
    const [, init] = fetchMock.mock.calls[0]
    expect(init.method).toBe('POST')
    expect(init.body).toBeInstanceOf(FormData)
    expect((init.body as FormData).get('sport')).toBe('swimming')
  })
})
