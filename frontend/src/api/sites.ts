import request from '@/utils/request'

export interface SiteRecord {
  id: string
  name: string
  domain: string
  template: string
  language: string
  offset: number
  is_active: boolean
  description: string | null
  url_patterns: SiteUrlPatterns
  chapter_pagination: ChapterPagination
  link_wheel: LinkWheelConfig
  recommend_modules: Record<string, any>
  created_at: string
  updated_at: string
}

export interface SiteUrlPatterns {
  novel_detail: string
  chapter_list: string
  chapter_read: string
  category_list: string
  search: string
}

export interface ChapterPagination {
  enabled: boolean
  method: string
  words_per_page: number
  pages_per_chapter: number
  page_param: string
  canonical_first_page: boolean
}

export interface LinkWheelConfig {
  enabled: boolean
  max_links_per_page: number
  link_section: string
  open_new_tab: boolean
  nofollow: boolean
}

export interface SiteCreatePayload {
  name: string
  domain: string
  template?: string
  language?: string
  offset?: number
  is_active?: boolean
  description?: string
  url_patterns?: Partial<SiteUrlPatterns>
  chapter_pagination?: Partial<ChapterPagination>
  link_wheel?: Partial<LinkWheelConfig>
  recommend_modules?: Record<string, any>
}

export const sitesApi = {
  list(): Promise<SiteRecord[]> {
    return request.get('/sites').then((r) => r.data)
  },

  get(id: string): Promise<SiteRecord> {
    return request.get(`/sites/${id}`).then((r) => r.data)
  },

  create(data: SiteCreatePayload): Promise<SiteRecord> {
    return request.post('/sites', data).then((r) => r.data)
  },

  update(id: string, data: Partial<SiteCreatePayload>): Promise<SiteRecord> {
    return request.put(`/sites/${id}`, data).then((r) => r.data)
  },

  delete(id: string): Promise<void> {
    return request.delete(`/sites/${id}`)
  },

  batchDelete(ids: string[]): Promise<any> {
    return request.post('/sites/batch-delete', { ids }).then((r) => r.data)
  },
}
