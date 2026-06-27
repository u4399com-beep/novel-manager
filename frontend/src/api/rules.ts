import request from '@/utils/request'

export interface RuleMeta {
  filename: string
  source_name: string
  description: string
  base_url: string
  version: string
}

export interface TestRequest {
  source_name: string
  section: 'search' | 'novel_info' | 'catalog' | 'chapter'
  test_url?: string
  keyword?: string
  book_id?: string
  chapter_url?: string
}

export interface TestResult {
  success: boolean
  url: string
  total?: number
  displayed?: number
  results: Record<string, any>[]
  error?: string
}

export const rulesApi = {
  list(): Promise<RuleMeta[]> {
    return request.get('/rules').then((r) => r.data)
  },

  get(sourceName: string): Promise<any> {
    return request.get(`/rules/${sourceName}`).then((r) => r.data)
  },

  save(sourceName: string, data: any): Promise<any> {
    return request.put(`/rules/${sourceName}`, { source_name: sourceName, data }).then((r) => r.data)
  },

  delete(sourceName: string): Promise<void> {
    return request.delete(`/rules/${sourceName}`)
  },

  test(params: TestRequest): Promise<TestResult> {
    return request.post('/rules/test', params).then((r) => r.data)
  },

  testPreview(params: TestRequest): Promise<TestResult> {
    return request.post('/rules/test-preview', params).then((r) => r.data)
  },
}
