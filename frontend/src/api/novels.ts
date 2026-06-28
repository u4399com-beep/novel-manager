import request from '@/utils/request'

export interface NovelRecord {
  id: string
  title: string
  author: string
  description: string | null
  cover_image_url: string | null
  source_url: string | null
  source_name: string | null
  status: string
  total_chapters: number
  categories: { id: number; name: string; slug: string }[]
  created_at: string
  updated_at: string
}

export interface NovelListResponse {
  items: NovelRecord[]
  total: number
  page: number
  size: number
  pages: number
}

export interface NovelParams {
  page?: number
  size?: number
  search?: string
  category_id?: number
  status?: string
  sort_by?: string
  sort_dir?: string
}

export interface NovelStatistics {
  total_chapters: number
  total_words: number
  average_words_per_chapter: number
  chapters_by_volume: Record<string, number>
  first_chapter_date: string | null
  latest_chapter_date: string | null
}

export interface CreateNovelPayload {
  title: string
  author: string
  description?: string
  cover_image_url?: string
  source_url?: string
  source_name?: string
  status?: string
  category_ids?: number[]
}

export const novelsApi = {
  list(params: NovelParams): Promise<NovelListResponse> {
    return request.get('/novels', { params }).then((r) => r.data)
  },

  get(id: string): Promise<NovelRecord> {
    return request.get(`/novels/${id}`).then((r) => r.data)
  },

  create(data: FormData | CreateNovelPayload): Promise<NovelRecord> {
    return request.post('/novels', data).then((r) => r.data)
  },

  update(id: string, data: Partial<CreateNovelPayload>): Promise<NovelRecord> {
    return request.put(`/novels/${id}`, data).then((r) => r.data)
  },

  delete(id: string): Promise<void> {
    return request.delete(`/novels/${id}`)
  },

  uploadCover(id: string, file: File): Promise<{ cover_image_url: string }> {
    const formData = new FormData()
    formData.append('file', file)
    return request.post(`/novels/${id}/cover`, formData).then((r) => r.data)
  },

  statistics(id: string): Promise<NovelStatistics> {
    return request.get(`/novels/${id}/statistics`).then((r) => r.data)
  },
}
