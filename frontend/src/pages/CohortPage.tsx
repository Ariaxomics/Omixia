import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { labApi, CohortVariant, CohortResult } from '../api/lab'
import LoadingSpinner from '../components/LoadingSpinner'

const VARIANT_TYPES = ['', 'snv', 'cnv', 'sv']
const TIERS = ['', 'tier_1', 'tier_2', 'tier_3', 'tier_4']

const TIER_BADGE: Record<string, string> = {
  tier_1: 'bg-red-100 text-red-700 border border-red-200',
  tier_2: 'bg-orange-100 text-orange-700 border border-orange-200',
  tier_3: 'bg-yellow-100 text-yellow-700 border border-yellow-200',
  tier_4: 'bg-gray-100 text-gray-600 border border-gray-200',
}

const TYPE_BADGE: Record<string, string> = {
  snv: 'bg-blue-100 text-blue-700',
  cnv: 'bg-purple-100 text-purple-700',
  sv: 'bg-teal-100 text-teal-700',
}

const TYPE_LABEL: Record<string, string> = {
  snv: 'SNV',
  cnv: 'CNV',
  sv: 'SV/Fusion',
}

const STATUS_BADGE: Record<string, string> = {
  concordant: 'bg-green-100 text-green-700',
  unreviewed: 'bg-gray-100 text-gray-500',
  discordant: 'bg-red-100 text-red-600',
  reviewed: 'bg-blue-100 text-blue-700',
}

function geneLabel(v: CohortVariant): string {
  if (v._variant_type === 'sv') {
    return `${v.gene_5prime ?? '?'} → ${v.gene_3prime ?? '?'}`
  }
  return v.gene ?? '—'
}

function detailLabel(v: CohortVariant): string {
  if (v._variant_type === 'snv') {
    const vaf = v.vaf != null ? ` (VAF ${(v.vaf * 100).toFixed(0)}%)` : ''
    return `${v.hgvsp ?? v.consequence ?? ''}${vaf}`
  }
  if (v._variant_type === 'cnv') {
    const cn = v.copy_number != null ? ` CN=${v.copy_number}` : ''
    return `${v.event_type ?? ''}${cn}`.replace(/_/g, ' ')
  }
  if (v._variant_type === 'sv') {
    return v.sv_type?.replace(/_/g, ' ') ?? '—'
  }
  return '—'
}

function computeGeneFrequency(results: CohortVariant[]) {
  const map: Record<string, { cases: Set<string>; types: Set<string> }> = {}
  for (const v of results) {
    const genes =
      v._variant_type === 'sv'
        ? [v.gene_5prime, v.gene_3prime].filter(Boolean) as string[]
        : [v.gene].filter(Boolean) as string[]
    for (const g of genes) {
      if (!map[g]) map[g] = { cases: new Set(), types: new Set() }
      map[g].cases.add(v.sample_assay_id)
      map[g].types.add(v._variant_type)
    }
  }
  return Object.entries(map)
    .map(([gene, { cases, types }]) => ({ gene, caseCount: cases.size, types: [...types] }))
    .sort((a, b) => b.caseCount - a.caseCount)
}

export default function CohortPage() {
  const [gene, setGene] = useState('')
  const [tier, setTier] = useState('')
  const [variantType, setVariantType] = useState('')
  const [assayId, setAssayId] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const [acknowledged, setAcknowledged] = useState(false)

  const { data, isLoading, refetch } = useQuery<CohortResult>({
    queryKey: ['cohort', gene, tier, variantType, assayId, acknowledged],
    queryFn: () => labApi.cohort({ gene, tier, variant_type: variantType, assay_id: assayId, acknowledge: acknowledged }),
    enabled: submitted,
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setAcknowledged(false)
    setSubmitted(true)
    refetch()
  }

  const handleAcknowledge = () => {
    setAcknowledged(true)
  }

  const results = data?.results ?? []
  const geneFreq = computeGeneFrequency(results)
  const uniqueCases = new Set(results.map((v) => v.sample_assay_id)).size
  const byType = results.reduce<Record<string, number>>((acc, v) => {
    acc[v._variant_type] = (acc[v._variant_type] ?? 0) + 1
    return acc
  }, {})

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">Cohort Query</h1>

      {/* Filter form */}
      <form onSubmit={handleSubmit} className="bg-white rounded-xl border border-gray-200 p-4 flex flex-wrap gap-3 items-end">
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">Gene</label>
          <input
            type="text"
            placeholder="e.g. TP53"
            value={gene}
            onChange={(e) => setGene(e.target.value)}
            className="border rounded-lg px-3 py-1.5 text-sm w-36 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">Tier</label>
          <select
            value={tier}
            onChange={(e) => setTier(e.target.value)}
            className="border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">All tiers</option>
            {TIERS.filter(Boolean).map((t) => (
              <option key={t} value={t}>{t.replace('_', ' ').toUpperCase()}</option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">Variant type</label>
          <select
            value={variantType}
            onChange={(e) => setVariantType(e.target.value)}
            className="border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            {VARIANT_TYPES.map((t) => (
              <option key={t} value={t}>{t ? TYPE_LABEL[t] : 'All types'}</option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">Assay ID</label>
          <input
            type="text"
            placeholder="Optional"
            value={assayId}
            onChange={(e) => setAssayId(e.target.value)}
            className="border rounded-lg px-3 py-1.5 text-sm w-40 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <button
          type="submit"
          className="px-5 py-1.5 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700"
        >
          Query
        </button>
      </form>

      {submitted && isLoading && <LoadingSpinner />}

      {/* Multi-version warning */}
      {submitted && !isLoading && data?.multi_version_warning && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 flex items-start gap-3">
          <span className="text-amber-500 text-lg mt-0.5">⚠</span>
          <div className="flex-1">
            <p className="font-medium text-amber-800 text-sm">Multiple panel versions detected</p>
            <p className="text-amber-700 text-sm mt-1">
              Results span <strong>{data.panel_versions.join(', ')}</strong>. Combining variants across different assay
              versions may affect comparability. Acknowledge to view results anyway.
            </p>
          </div>
          <button
            onClick={handleAcknowledge}
            className="px-4 py-1.5 bg-amber-600 text-white rounded-lg text-sm font-medium hover:bg-amber-700 shrink-0"
          >
            Acknowledge &amp; show results
          </button>
        </div>
      )}

      {/* Results */}
      {submitted && !isLoading && !data?.multi_version_warning && results.length > 0 && (
        <>
          {/* Summary cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div className="bg-white rounded-xl border border-gray-200 px-5 py-4">
              <p className="text-xs text-gray-500 uppercase tracking-wide font-medium">Total variants</p>
              <p className="text-3xl font-bold text-gray-900 mt-1">{data?.total ?? 0}</p>
            </div>
            <div className="bg-white rounded-xl border border-gray-200 px-5 py-4">
              <p className="text-xs text-gray-500 uppercase tracking-wide font-medium">Unique cases</p>
              <p className="text-3xl font-bold text-gray-900 mt-1">{uniqueCases}</p>
            </div>
            <div className="bg-white rounded-xl border border-gray-200 px-5 py-4">
              <p className="text-xs text-gray-500 uppercase tracking-wide font-medium">Unique genes</p>
              <p className="text-3xl font-bold text-gray-900 mt-1">{geneFreq.length}</p>
            </div>
            <div className="bg-white rounded-xl border border-gray-200 px-5 py-4">
              <p className="text-xs text-gray-500 uppercase tracking-wide font-medium">By type</p>
              <div className="flex flex-wrap gap-1 mt-2">
                {Object.entries(byType).map(([type, count]) => (
                  <span key={type} className={`px-2 py-0.5 rounded text-xs font-medium ${TYPE_BADGE[type] ?? ''}`}>
                    {TYPE_LABEL[type] ?? type} {count}
                  </span>
                ))}
              </div>
            </div>
          </div>

          {/* Gene frequency */}
          {geneFreq.length > 0 && (
            <div>
              <h2 className="text-lg font-semibold text-gray-800 mb-3">Gene Recurrence</h2>
              <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 border-b">
                    <tr>
                      <th className="px-4 py-3 text-left font-medium text-gray-600">Gene</th>
                      <th className="px-4 py-3 text-left font-medium text-gray-600">Cases</th>
                      <th className="px-4 py-3 text-left font-medium text-gray-600">Variant types</th>
                      <th className="px-4 py-3 text-left font-medium text-gray-600">Frequency bar</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {geneFreq.map(({ gene: g, caseCount, types }) => (
                      <tr key={g} className="hover:bg-gray-50">
                        <td className="px-4 py-3 font-medium text-gray-900">{g}</td>
                        <td className="px-4 py-3 text-gray-700 font-semibold">{caseCount}</td>
                        <td className="px-4 py-3">
                          <div className="flex gap-1">
                            {types.map((t) => (
                              <span key={t} className={`px-2 py-0.5 rounded text-xs font-medium ${TYPE_BADGE[t] ?? ''}`}>
                                {TYPE_LABEL[t] ?? t}
                              </span>
                            ))}
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <div
                              className="h-2 rounded-full bg-blue-400"
                              style={{ width: `${Math.max(8, (caseCount / uniqueCases) * 120)}px` }}
                            />
                            <span className="text-xs text-gray-400">{uniqueCases > 0 ? Math.round((caseCount / uniqueCases) * 100) : 0}%</span>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Variant results table */}
          <div>
            <h2 className="text-lg font-semibold text-gray-800 mb-3">Variant Results</h2>
            <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b">
                  <tr>
                    <th className="px-4 py-3 text-left font-medium text-gray-600">Type</th>
                    <th className="px-4 py-3 text-left font-medium text-gray-600">Gene</th>
                    <th className="px-4 py-3 text-left font-medium text-gray-600">Detail</th>
                    <th className="px-4 py-3 text-left font-medium text-gray-600">Case</th>
                    <th className="px-4 py-3 text-left font-medium text-gray-600">Assay</th>
                    <th className="px-4 py-3 text-left font-medium text-gray-600">Tier</th>
                    <th className="px-4 py-3 text-left font-medium text-gray-600">Review</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {results.map((v, i) => {
                    const tier = v.review_current?.tier
                    const status = v.review_current?.consensus_status ?? v.review_current?.status ?? 'unreviewed'
                    return (
                      <tr key={i} className="hover:bg-gray-50">
                        <td className="px-4 py-3">
                          <span className={`px-2 py-0.5 rounded text-xs font-medium ${TYPE_BADGE[v._variant_type] ?? ''}`}>
                            {TYPE_LABEL[v._variant_type] ?? v._variant_type}
                          </span>
                        </td>
                        <td className="px-4 py-3 font-medium text-gray-900">{geneLabel(v)}</td>
                        <td className="px-4 py-3 text-gray-600 text-xs">{detailLabel(v)}</td>
                        <td className="px-4 py-3 text-gray-700 text-xs">{v.sample_assay_id}</td>
                        <td className="px-4 py-3 text-gray-500 text-xs">{v._assay_id ?? '—'}</td>
                        <td className="px-4 py-3">
                          {tier ? (
                            <span className={`px-2 py-0.5 rounded text-xs font-medium ${TIER_BADGE[tier] ?? ''}`}>
                              {tier.replace('_', ' ').toUpperCase()}
                            </span>
                          ) : (
                            <span className="text-gray-400 text-xs">—</span>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          <span className={`px-2 py-0.5 rounded text-xs font-medium capitalize ${STATUS_BADGE[status] ?? 'bg-gray-100 text-gray-500'}`}>
                            {status.replace(/_/g, ' ')}
                          </span>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {submitted && !isLoading && !data?.multi_version_warning && results.length === 0 && (
        <div className="text-center py-16 text-gray-400 text-sm">No variants found matching your filters</div>
      )}
    </div>
  )
}
