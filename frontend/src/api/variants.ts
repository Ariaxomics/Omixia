import client from './client'

export interface ReviewPayload {
  tier: string | null
  is_artifact: boolean
  interpretation: string
  note: string
  bypass_justification?: string
}

export const variantsApi = {
  // SNVs
  listSnvs: async (assayId: string) => {
    const res = await client.get(`/sample-assays/${assayId}/snvs`)
    return res.data.data as Record<string, unknown>[]
  },
  getSnv: async (assayId: string, chrom: string, pos: string, ref: string, alt: string) => {
    const res = await client.get(`/sample-assays/${assayId}/snvs/${chrom}/${pos}/${ref}/${alt}`)
    return res.data.data as Record<string, unknown>
  },
  reviewSnv: async (assayId: string, chrom: string, pos: string, ref: string, alt: string, payload: ReviewPayload) => {
    const res = await client.post(`/sample-assays/${assayId}/snvs/${chrom}/${pos}/${ref}/${alt}/review`, payload)
    return res.data
  },

  // CNVs
  listCnvs: async (assayId: string) => {
    const res = await client.get(`/sample-assays/${assayId}/cnvs`)
    return res.data.data as Record<string, unknown>[]
  },
  reviewCnv: async (assayId: string, gene: string, payload: ReviewPayload) => {
    const res = await client.post(`/sample-assays/${assayId}/cnvs/${gene}/review`, payload)
    return res.data
  },

  // SVs
  listSvs: async (assayId: string) => {
    const res = await client.get(`/sample-assays/${assayId}/svs`)
    return res.data.data as Record<string, unknown>[]
  },
  reviewSv: async (assayId: string, svId: string, payload: ReviewPayload) => {
    const res = await client.post(`/sample-assays/${assayId}/svs/${svId}/review`, payload)
    return res.data
  },

  // Preflight
  preflight: async (assayId: string) => {
    const res = await client.get(`/sample-assays/${assayId}/preflight`)
    return res.data as { data: Record<string, unknown>[]; all_passed: boolean }
  },

  // Biomarkers
  getBiomarkers: async (assayId: string) => {
    const res = await client.get(`/sample-assays/${assayId}/biomarkers`)
    return res.data.data as Record<string, unknown> | null
  },
  confirmBiomarkers: async (assayId: string, payload: { reviewer_note: string; discordance_acknowledged: boolean }) => {
    const res = await client.post(`/sample-assays/${assayId}/biomarkers/confirm`, payload)
    return res.data.data
  },

  // Callsets
  listCallsets: async (assayId: string) => {
    const res = await client.get(`/sample-assays/${assayId}/callsets`)
    return res.data.data as Record<string, unknown>[]
  },
}
