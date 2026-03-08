import client from './client'

export const labApi = {
  dashboard: async () => {
    const res = await client.get('/lab/dashboard')
    return res.data.data as Record<string, unknown>
  },
  gapAnalysis: async (gene: string, assayId?: string) => {
    const res = await client.get('/gap-analysis', { params: { gene, assay_id: assayId } })
    return res.data.data as Record<string, unknown>[]
  },
  cohort: async (params: { gene?: string; tier?: string; variant_type?: string; assay_id?: string }) => {
    const res = await client.get('/cohort', { params })
    return res.data.data as Record<string, unknown>
  },
}
