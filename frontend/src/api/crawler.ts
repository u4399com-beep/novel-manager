import request from '@/utils/request'

export interface CrawlerTask {
  id: string; novel_id: string; status: string
  chapters_found: number; chapters_added: number
  error_message: string | null
  started_at: string | null; finished_at: string | null; created_at: string
}
export interface CrawlerSource { source_name: string; base_url: string; description: string }

export interface SearchPreviewResult {
  novel_title: string; novel_author: string; source_name: string; total_results: number
  candidates: Array<{ title: string; author: string; url: string; book_id: string; _score: number }>
  best_match: { title: string; author: string; url: string; book_id: string; _score: number } | null
}

export interface PagePreviewResult {
  page_url: string; page_from?: number; page_to?: number; pages_fetched?: number
  total: number; novel_count: number; chapter_count: number
  novels: Array<{ title: string; url: string; book_id: string; cover_url?: string; is_chapter?: boolean }>
  chapters: Array<{ title: string; url: string; book_id: string; cover_url?: string; is_chapter?: boolean }>
}

export interface PageTriggerResult {
  message: string; imported: number; skipped: number; task_ids: string[]
}

export const crawlerApi = {
  sources: () => request.get('/crawler/sources').then(r => r.data),

  trigger: (novelId: string, sourceName?: string, mode: 'direct'|'search'='direct') =>
    request.post('/crawler/trigger', { novel_id: novelId, source_name: sourceName, mode }).then(r => r.data),

  triggerBatch: (novelIds: string[], sourceName?: string, mode: 'direct'|'search'='direct') =>
    request.post('/crawler/trigger-batch', { novel_ids: novelIds, source_name: sourceName, mode }).then(r => r.data),

  searchPreview: (novelId: string, sourceName: string): Promise<SearchPreviewResult> =>
    request.post('/crawler/search-preview', { novel_id: novelId, source_name: sourceName }).then(r => r.data),

  // -- Page extraction --
  pagePreview: (pageUrl: string, sourceName?: string, pageFrom?: number, pageTo?: number): Promise<PagePreviewResult> =>
    request.post('/crawler/page-preview', { page_url: pageUrl, source_name: sourceName, page_from: pageFrom || 1, page_to: pageTo || 1 }).then(r => r.data),

  pageTest: (pageUrl: string, sourceName?: string, pageFrom?: number, pageTo?: number, selectedBookIds?: string[]): Promise<{total:number,passed:number,failed:number,novels:any[]}> =>
    request.post('/crawler/page-test', { page_url: pageUrl, source_name: sourceName, page_from: pageFrom || 1, page_to: pageTo || 1, selected_book_ids: selectedBookIds }).then(r => r.data),

  triggerPage: (pageUrl: string, sourceName: string, selectedBookIds?: string[], pageFrom?: number, pageTo?: number): Promise<PageTriggerResult> =>
    request.post('/crawler/trigger-page', { page_url: pageUrl, source_name: sourceName, selected_book_ids: selectedBookIds, page_from: pageFrom || 1, page_to: pageTo || 1 }).then(r => r.data),

  // -- Tasks --
  listTasks: (params?: { novel_id?: string; status?: string; page?: number; size?: number }) =>
    request.get('/crawler/tasks', { params }).then(r => r.data),
  getTask: (id: string): Promise<CrawlerTask> => request.get(`/crawler/tasks/${id}`).then(r => r.data),
  deleteTask: (id: string) => request.delete(`/crawler/tasks/${id}`),
  updateTask: (id: string, data: any) => request.put(`/crawler/tasks/${id}`, data).then(r => r.data),
  startTask: (id: string): Promise<CrawlerTask> => request.post(`/crawler/tasks/${id}/start`).then(r => r.data),
  stopTask: (id: string): Promise<CrawlerTask> => request.post(`/crawler/tasks/${id}/stop`).then(r => r.data),
  retryTask: (id: string): Promise<CrawlerTask> => request.post(`/crawler/tasks/${id}/retry`).then(r => r.data),
  batchDeleteTasks: (ids: string[]): Promise<any> => request.post('/crawler/tasks/batch-delete', { ids }).then(r => r.data),

  // -- Rules --
  listRules: () => request.get('/rules').then(r => r.data),
  getRule: (name: string) => request.get(`/rules/${name}`).then(r => r.data),
  saveRule: (name: string, data: any) => request.put(`/rules/${name}`, { source_name: name, data }).then(r => r.data),
  deleteRule: (name: string) => request.delete(`/rules/${name}`),
}
