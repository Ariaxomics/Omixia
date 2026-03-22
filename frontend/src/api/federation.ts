import client from './client'

export const federationApi = {
  listExports: async () => {
    const res = await client.get('/federation/exports')
    return res.data.data as Record<string, unknown>[]
  },
  eligibleCount: async () => {
    const res = await client.get('/federation/eligible')
    return (res.data.data as { count: number }).count
  },
  export: async (labId: string) => {
    const res = await client.post('/federation/export', { lab_id: labId })
    return res.data.data as Record<string, unknown>
  },
}
