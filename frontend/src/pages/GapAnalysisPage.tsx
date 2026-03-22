import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { labApi } from '../api/lab'
import { useAuth } from '../contexts/AuthContext'
import LoadingSpinner from '../components/LoadingSpinner'

interface AssayEntry {
  assay_id: string
  version: string
  panel_size: number
}

interface UncoveredCase {
  sample_assay_id: string
  sample_id: string
  assay_id: string
  assay_version: string
  status: string
  _gap_reason: string
}

interface GapAnalysisResult {
  gene: string
  covered_by: AssayEntry[]
  not_covered_by: AssayEntry[]
  uncovered_cases: UncoveredCase[]
  uncovered_case_count: number
}

export default function GapAnalysisPage() {
  const { user } = useAuth()
  const allowed = user?.role === 'lab_director' || user?.role === 'admin'
  const [gene, setGene] = useState('')
  const [assayId, setAssayId] = useState('')
  const [submittedGene, setSubmittedGene] = useState('')
  const [submittedAssayId, setSubmittedAssayId] = useState('')

  const { data, isLoading, error } = useQuery<GapAnalysisResult>({
    queryKey: ['gap-analysis', submittedGene, submittedAssayId],
    queryFn: () => labApi.gapAnalysis(submittedGene, submittedAssayId || undefined) as Promise<GapAnalysisResult>,
    enabled: !!submittedGene,
  })

  if (!allowed) {
    return <div className="text-center py-20 text-gray-400">Access restricted to Lab Director</div>
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!gene) return
    setSubmittedGene(gene)
    setSubmittedAssayId(assayId)
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

      {!!submittedGene && (
        <p className="text-xs bg-yellow-100 border border-yellow-300 rounded p-2 mb-2 font-mono">
          submitted: "{submittedGene}" | loading: {String(isLoading)} | hasData: {String(!!data)} | error: {error ? String(error) : 'none'}
        </p>
      )}

      {!!submittedGene && isLoading && <LoadingSpinner />}

      {!!submittedGene && error && (
        <p className="text-red-600 text-sm">Failed to load gap analysis results.</p>
      )}

      {!!submittedGene && !isLoading && data && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-4">
            <div className="bg-green-50 border border-green-200 rounded-xl p-4">
              <p className="text-sm font-semibold text-green-800 mb-2">
                Covered by {data.covered_by.length} assay version{data.covered_by.length !== 1 ? 's' : ''}
              </p>
              {data.covered_by.length === 0 ? (
                <p className="text-xs text-green-600">None</p>
              ) : (
                <ul className="text-xs text-green-700 space-y-0.5">
                  {data.covered_by.map((a) => (
                    <li key={a.assay_id + a.version}>{a.assay_id} v{a.version} ({a.panel_size} genes)</li>
                  ))}
                </ul>
              )}
            </div>
            <div className="bg-red-50 border border-red-200 rounded-xl p-4">
              <p className="text-sm font-semibold text-red-800 mb-2">
                Not covered by {data.not_covered_by.length} assay version{data.not_covered_by.length !== 1 ? 's' : ''}
              </p>
              {data.not_covered_by.length === 0 ? (
                <p className="text-xs text-red-600">None</p>
              ) : (
                <ul className="text-xs text-red-700 space-y-0.5">
                  {data.not_covered_by.map((a) => (
                    <li key={a.assay_id + a.version}>{a.assay_id} v{a.version} ({a.panel_size} genes)</li>
                  ))}
                </ul>
              )}
            </div>
          </div>

          <div>
            <h2 className="text-sm font-semibold text-gray-700 mb-2">
              Uncovered cases ({data.uncovered_case_count})
            </h2>
            {data.uncovered_case_count === 0 ? (
              <p className="text-center text-gray-400 py-6 text-sm bg-white rounded-xl border border-gray-200">
                No cases affected — all cases used an assay that covers {data.gene}
              </p>
            ) : (
              <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
                    <tr>
                      <th className="px-4 py-2 text-left">Sample ID</th>
                      <th className="px-4 py-2 text-left">Assay</th>
                      <th className="px-4 py-2 text-left">Version</th>
                      <th className="px-4 py-2 text-left">Status</th>
                      <th className="px-4 py-2 text-left">Gap Reason</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {data.uncovered_cases.map((c) => (
                      <tr key={c.sample_assay_id} className="hover:bg-gray-50">
                        <td className="px-4 py-2 font-mono text-xs">{c.sample_id}</td>
                        <td className="px-4 py-2">{c.assay_id}</td>
                        <td className="px-4 py-2">{c.assay_version}</td>
                        <td className="px-4 py-2">{c.status}</td>
                        <td className="px-4 py-2 text-gray-500 text-xs">{c._gap_reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
