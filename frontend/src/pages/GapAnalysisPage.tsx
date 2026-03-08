import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { labApi } from '../api/lab'
import { useAuth } from '../contexts/AuthContext'
import LoadingSpinner from '../components/LoadingSpinner'

export default function GapAnalysisPage() {
  const { user } = useAuth()
  const allowed = user?.role === 'lab_director'
  const [gene, setGene] = useState('')
  const [assayId, setAssayId] = useState('')
  const [submitted, setSubmitted] = useState(false)

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['gap-analysis', gene, assayId],
    queryFn: () => labApi.gapAnalysis(gene, assayId || undefined),
    enabled: false,
  })

  if (!allowed) {
    return <div className="text-center py-20 text-gray-400">Access restricted to Lab Director</div>
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!gene) return
    setSubmitted(true)
    refetch()
  }

  return (
    <div>
      <h1 className="text-xl font-bold text-gray-900 mb-5">Gap Analysis</h1>
      <form onSubmit={handleSubmit} className="flex gap-3 mb-6">
        <input
          type="text"
          placeholder="Gene (e.g. BRCA1)"
          value={gene}
          onChange={(e) => setGene(e.target.value)}
          className="border rounded-lg px-3 py-1.5 text-sm w-40 focus:outline-none focus:ring-2 focus:ring-blue-500"
          required
        />
        <input
          type="text"
          placeholder="Assay ID (optional)"
          value={assayId}
          onChange={(e) => setAssayId(e.target.value)}
          className="border rounded-lg px-3 py-1.5 text-sm w-48 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <button
          type="submit"
          className="px-4 py-1.5 bg-blue-600 text-white rounded text-sm font-medium hover:bg-blue-700"
        >
          Analyse
        </button>
      </form>

      {submitted && isLoading && <LoadingSpinner />}
      {submitted && !isLoading && data && (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
              <tr>
                {Object.keys((data as Record<string, unknown>[])[0] ?? {}).map((k) => (
                  <th key={k} className="px-4 py-2 text-left">{k.replace(/_/g, ' ')}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {(data as Record<string, unknown>[]).map((row, i) => (
                <tr key={i} className="hover:bg-gray-50">
                  {Object.values(row).map((v, j) => (
                    <td key={j} className="px-4 py-2">{String(v)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {(data as unknown[]).length === 0 && (
            <p className="text-center text-gray-400 py-6 text-sm">No gaps found for {gene}</p>
          )}
        </div>
      )}
    </div>
  )
}
