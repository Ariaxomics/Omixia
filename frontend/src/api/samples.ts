import client from './client'

export const samplesApi = {
  list: async () => {
    const res = await client.get('/samples')
    return res.data.data as Record<string, unknown>[]
  },
  get: async (sampleId: string) => {
    const res = await client.get(`/samples/${sampleId}`)
    return res.data.data as Record<string, unknown>
  },
  getAssays: async (sampleId: string) => {
    const res = await client.get(`/samples/${sampleId}/assays`)
    return res.data.data as Record<string, unknown>[]
  },
  getSampleAssay: async (assayId: string) => {
    const res = await client.get(`/sample-assays/${assayId}`)
    return res.data.data as Record<string, unknown>
  },
  getSummary: async (assayId: string) => {
    const res = await client.get(`/sample-assays/${assayId}/summary`)
    return res.data.data as Record<string, unknown>
  },
  assign: async (assayId: string, reviewers: string[], bioinformatician: string) => {
    const res = await client.post(`/sample-assays/${assayId}/assign`, { reviewers, bioinformatician })
    return res.data.data
  },
}
