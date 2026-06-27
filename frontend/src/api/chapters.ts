import request from '@/utils/request'

export interface ChapterRecord {
  id: string
  novel_id: string
  title: string
  sort_order: number
  word_count: number
  source_url: string | null
  is_published: boolean
  created_at: string
  updated_at: string
}

export interface ChapterDetail extends ChapterRecord {
  content: string | null
}

export interface ChapterListResponse {
  items: ChapterRecord[]
  total: number
  page: number
  size: number
  pages: number
}

export const chaptersApi = {
  list(novelId: string, params?: { page?: number; size?: number }): Promise<ChapterListResponse> {
    return request.get(`/novels/${novelId}/chapters`, { params }).then((r) => r.data)
  },

  get(novelId: string, chapterId: string): Promise<ChapterDetail> {
    return request.get(`/novels/${novelId}/chapters/${chapterId}`).then((r) => r.data)
  },

  create(novelId: string, data: Record<string, any>): Promise<ChapterRecord> {
    return request.post(`/novels/${novelId}/chapters`, data).then((r) => r.data)
  },

  update(novelId: string, chapterId: string, data: Record<string, any>): Promise<ChapterRecord> {
    return request.put(`/novels/${novelId}/chapters/${chapterId}`, data).then((r) => r.data)
  },

  delete(novelId: string, chapterId: string): Promise<void> {
    return request.delete(`/novels/${novelId}/chapters/${chapterId}`)
  },

  batchCreate(novelId: string, chapters: Record<string, any>[]): Promise<ChapterRecord[]> {
    return request.post(`/novels/${novelId}/chapters/batch`, { chapters }).then((r) => r.data)
  },

  reorder(novelId: string, orders: { id: string; sort_order: number }[]): Promise<any> {
    return request.put(`/novels/${novelId}/chapters/reorder`, { orders }).then((r) => r.data)
  },

  batchDelete(novelId: string, ids: string[]): Promise<any> {
    return request.delete(`/novels/${novelId}/chapters/batch`, { data: { ids } }).then((r) => r.data)
  },
}
