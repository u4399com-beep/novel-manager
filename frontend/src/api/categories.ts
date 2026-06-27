import request from '@/utils/request'

export interface CategoryRecord {
  id: number
  name: string
  slug: string
  description: string | null
  sort_order: number
}

export const categoriesApi = {
  list(): Promise<CategoryRecord[]> {
    return request.get('/categories').then((r) => r.data)
  },

  create(data: Record<string, any>): Promise<CategoryRecord> {
    return request.post('/categories', data).then((r) => r.data)
  },

  update(id: number, data: Record<string, any>): Promise<CategoryRecord> {
    return request.put(`/categories/${id}`, data).then((r) => r.data)
  },

  delete(id: number): Promise<void> {
    return request.delete(`/categories/${id}`)
  },
}
