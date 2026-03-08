import client from './client'

export interface KnowledgeFilters {
  gene?: string
  variant_type?: string
  tier?: string
  disease_group?: string
  q?: string
}

export interface KnowledgePayload {
  gene: string
  variant_type: string
  hgvsp?: string
  tier: string
  disease_group: string
  disease_subtype?: string
  interpretation: string
  evidence_summary: string
  pmids?: string[]
  change_note?: string
}

export const knowledgeApi = {
  list: async (filters: KnowledgeFilters = {}) => {
    const res = await client.get('/knowledge', { params: filters })
    return res.data.data as Record<string, unknown>[]
  },
  search: async (q: string, filters: KnowledgeFilters = {}) => {
    const res = await client.get('/knowledge/search', { params: { q, ...filters } })
    return res.data.data as Record<string, unknown>[]
  },
  get: async (id: string) => {
    const res = await client.get(`/knowledge/${id}`)
    return res.data.data as Record<string, unknown>
  },
  create: async (payload: KnowledgePayload) => {
    const res = await client.post('/knowledge', payload)
    return res.data.data
  },
  update: async (id: string, payload: Partial<KnowledgePayload>) => {
    const res = await client.put(`/knowledge/${id}`, payload)
    return res.data.data
  },
}
