import client from './client'

export const reportsApi = {
  list: async (assayId: string) => {
    const res = await client.get(`/sample-assays/${assayId}/reports`)
    return res.data.data as Record<string, unknown>[]
  },
  create: async (assayId: string) => {
    const res = await client.post(`/sample-assays/${assayId}/reports`, {})
    return res.data.data
  },
  get: async (reportId: string) => {
    const res = await client.get(`/reports/${reportId}`)
    return res.data.data as Record<string, unknown>
  },
  signOff: async (reportId: string) => {
    const res = await client.post(`/reports/${reportId}/sign-off`, {})
    return res.data.data
  },
  finalise: async (reportId: string) => {
    const res = await client.post(`/reports/${reportId}/finalise`, {})
    return res.data.data
  },
  export: async (reportId: string) => {
    const res = await client.get(`/reports/${reportId}/export`)
    return res.data
  },
  issuePortalToken: async (reportId: string) => {
    const res = await client.post(`/reports/${reportId}/portal-token`, {})
    return res.data.data as { portal_url: string; expires_at: string }
  },
}
