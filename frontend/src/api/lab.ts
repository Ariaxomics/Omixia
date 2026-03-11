import client from './client'

export interface CohortVariant {
  sample_assay_id: string
  _variant_type: 'snv' | 'cnv' | 'sv'
  _assay_id: string | null
  _assay_version: string | null
  gene?: string
  gene_5prime?: string
  gene_3prime?: string
  hgvsp?: string
  consequence?: string
  vaf?: number
  event_type?: string
  copy_number?: number
  sv_type?: string
  review_current?: {
    tier: string | null
    status: string
    consensus_status: string
    interpretation: string
  }
}

export interface CohortResult {
  results: CohortVariant[]
  total: number
  panel_versions: string[]
  multi_version_warning: boolean
  requires_acknowledgment: boolean
}

export const labApi = {
  dashboard: async () => {
    const res = await client.get('/lab/dashboard')
    return res.data.data as Record<string, unknown>
  },
  gapAnalysis: async (gene: string, assayId?: string) => {
    const res = await client.get('/gap-analysis', { params: { gene, assay_id: assayId } })
    return res.data.data as Record<string, unknown>[]
  },
  cohort: async (params: { gene?: string; tier?: string; variant_type?: string; assay_id?: string; acknowledge?: boolean }) => {
    const { acknowledge, ...rest } = params
    const res = await client.get('/cohort', { params: { ...rest, ...(acknowledge ? { acknowledge: '1' } : {}) } })
    return res.data.data as CohortResult
  },
}
