import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { labApi } from '../api/lab'
import LoadingSpinner from '../components/LoadingSpinner'

const VARIANT_TYPES = ['', 'snv', 'cnv', 'sv']
const TIERS = ['', 'tier_1', 'tier_2', 'tier_3', 'tier_4']

export default function CohortPage() {
  const [gene, setGene] = useState('')
  const [tier, setTier] = useState('')
  const [variantType, setVariantType] = useState('')
  const [assayId, setAssayId] = useState('')
  const [submitted, setSubmitted] = useState(false)

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['cohort', gene, tier, variantType, assayId],
    queryFn: () => labApi.cohort({ gene, tier, variant_type: variantType, assay_id: assayId }),
    enabled: false,
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitted(true)
    refetch()
  }

  return (
    <div>
      <h1 className="text-xl font-bold text-gray-900 mb-5">Cohort Query</h1>
      <form onSubmit={handleSubmit} className="flex flex-wrap gap-3 mb-6">
        <input
          type="text"
          placeholder="Gene (e.g. TP53)"
          value={gene}
          onChange={(e) => setGene(e.target.value)}
          className="border rounded-lg px-3 py-1.5 text-sm w-36 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <select
          value={tier}
          onChange={(e) => setTier(e.target.value)}
          className="border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="">All tiers</option>
          {TIERS.filter(Boolean).map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <select
          value={variantType}
          onChange={(e) => setVariantType(e.target.value)}
          className="border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {VARIANT_TYPES.map((t) => <option key={t} value={t}>{t || 'All types'}</option>)}
        </select>
        <input
          type="text"
          placeholder="Assay ID (optional)"
          value={assayId}
          onChange={(e) => setAssayId(e.target.value)}
          className="border rounded-lg px-3 py-1.5 text-sm w-40 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <button
          type="submit"
          className="px-4 py-1.5 bg-blue-600 text-white rounded text-sm font-medium hover:bg-blue-700"
        >
          Query
        </button>
      </form>

      {submitted && isLoading && <LoadingSpinner />}

      {submitted && !isLoading && data && (
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <h2 className="font-semibold text-gray-900 mb-3">Results</h2>
          <pre className="text-xs bg-gray-50 rounded p-3 overflow-auto max-h-96">
            {JSON.stringify(data, null, 2)}
          </pre>
        </div>
      )}
    </div>
  )
}
