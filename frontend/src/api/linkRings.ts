import request from '@/utils/request'

export interface LinkRingRecord {
  id: string
  name: string
  ring_type: string
  site_id: string | null
  max_links: number
  display_mode: string
  link_format: string
  open_new_tab: boolean
  nofollow: boolean
  is_active: boolean
  selection_rules: Record<string, any> | null
  created_at: string
  updated_at: string
}

export interface LinkRingTarget {
  id: string
  link_ring_id: string
  source_site_id: string | null
  source_novel_id: string | null
  target_site_id: string | null
  target_novel_id: string | null
  target_url: string | null
  anchor_text: string
  sort_order: number
  is_active: boolean
}

export interface LinkRingCreatePayload {
  name: string
  ring_type?: string
  site_id?: string
  max_links?: number
  display_mode?: string
  link_format?: string
  open_new_tab?: boolean
  nofollow?: boolean
  is_active?: boolean
  selection_rules?: Record<string, any> | null
}

export interface TargetCreatePayload {
  source_site_id?: string
  source_novel_id?: string
  target_site_id?: string
  target_novel_id?: string
  target_url?: string
  anchor_text?: string
  sort_order?: number
  is_active?: boolean
}

export const linkRingsApi = {
  list(): Promise<LinkRingRecord[]> {
    return request.get('/link-rings').then((r) => r.data)
  },

  get(id: string): Promise<LinkRingRecord> {
    return request.get(`/link-rings/${id}`).then((r) => r.data)
  },

  create(data: LinkRingCreatePayload): Promise<LinkRingRecord> {
    return request.post('/link-rings', data).then((r) => r.data)
  },

  update(id: string, data: Partial<LinkRingCreatePayload>): Promise<LinkRingRecord> {
    return request.put(`/link-rings/${id}`, data).then((r) => r.data)
  },

  delete(id: string): Promise<void> {
    return request.delete(`/link-rings/${id}`)
  },

  // Targets
  listTargets(ringId: string): Promise<LinkRingTarget[]> {
    return request.get(`/link-rings/${ringId}/targets`).then((r) => r.data)
  },

  createTarget(ringId: string, data: TargetCreatePayload): Promise<LinkRingTarget> {
    return request.post(`/link-rings/${ringId}/targets`, data).then((r) => r.data)
  },

  updateTarget(ringId: string, targetId: string, data: Partial<TargetCreatePayload>): Promise<LinkRingTarget> {
    return request.put(`/link-rings/${ringId}/targets/${targetId}`, data).then((r) => r.data)
  },

  deleteTarget(ringId: string, targetId: string): Promise<void> {
    return request.delete(`/link-rings/${ringId}/targets/${targetId}`)
  },
}
