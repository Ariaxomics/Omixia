import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { samplesApi } from '../api/samples'
import LoadingSpinner from '../components/LoadingSpinner'
import Badge from '../components/Badge'

export default function SamplesPage() {
  const [search, setSearch] = useState('')
  const { data: samples, isLoading } = useQuery({
    queryKey: ['samples'],
    queryFn: samplesApi.list,
  })

  const filtered = (samples ?? []).filter((s: Record<string, unknown>) => {
    const q = search.toLowerCase()
    return (
      !q ||
      (s.sample_id as string)?.toLowerCase().includes(q) ||
      (s.patient_pseudonym_id as string)?.toLowerCase().includes(q) ||
      (s.disease_subtype as string)?.toLowerCase().includes(q)
    )
  })

  return (
    <div>
      <div className="mb-5 flex items-center justify-between">
        <h1 className="text-xl font-bold text-gray-900">Samples</h1>
        <input
          type="text"
          placeholder="Search samples…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="border rounded-lg px-3 py-1.5 text-sm w-56 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      {isLoading ? (
        <LoadingSpinner />
      ) : (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
              <tr>
                <th className="px-4 py-3 text-left">Sample ID</th>
                <th className="px-4 py-3 text-left">Patient ID</th>
                <th className="px-4 py-3 text-left">Disease Group</th>
                <th className="px-4 py-3 text-left">Disease Subtype</th>
                <th className="px-4 py-3 text-left">Status</th>
                <th className="px-4 py-3 text-left">Assays</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {filtered.map((s: Record<string, unknown>) => (
                <SampleRow key={s.sample_id as string} sample={s} />
              ))}
            </tbody>
          </table>
          {filtered.length === 0 && (
            <p className="text-center text-gray-400 py-10">No samples found</p>
          )}
        </div>
      )}
    </div>
  )
}

function SampleRow({ sample }: { sample: Record<string, unknown> }) {
  const [expanded, setExpanded] = useState(false)
  const navigate = useNavigate()

  const { data: assays, isLoading } = useQuery({
    queryKey: ['sample-assays', sample.sample_id],
    queryFn: () => samplesApi.getAssays(sample.sample_id as string),
    enabled: expanded,
  })

  return (
    <>
      <tr
        className="hover:bg-gray-50 cursor-pointer"
        onClick={() => setExpanded((v) => !v)}
      >
        <td className="px-4 py-3 font-mono text-xs">{sample.sample_id as string}</td>
        <td className="px-4 py-3">{(sample.patient_pseudonym_id as string) || '—'}</td>
        <td className="px-4 py-3 text-gray-600">{(sample.disease_group as string) || '—'}</td>
        <td className="px-4 py-3 text-gray-600">{(sample.disease_subtype as string) || '—'}</td>
        <td className="px-4 py-3 text-gray-400 text-xs">
          {(sample.status as string) || '—'}
        </td>
        <td className="px-4 py-3 text-gray-400">{expanded ? '▲' : '▼'}</td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={6} className="bg-blue-50 px-6 py-3">
            {isLoading ? (
              <span className="text-sm text-gray-400">Loading assays…</span>
            ) : (assays ?? []).length === 0 ? (
              <span className="text-sm text-gray-400">No assays</span>
            ) : (
              <div className="flex flex-wrap gap-2">
                {(assays ?? []).map((a: Record<string, unknown>) => (
                  <button
                    key={a.sample_assay_id as string}
                    onClick={(e) => {
                      e.stopPropagation()
                      navigate(`/samples/${sample.sample_id}/assays/${a.sample_assay_id}`)
                    }}
                    className="px-3 py-1.5 bg-white border border-blue-200 rounded-lg text-sm hover:bg-blue-100 transition-colors"
                  >
                    {(a.assay_id as string) || (a._id as string)}
                    {(a.status as string) && <Badge value={a.status as string} className="ml-2" />}
                  </button>
                ))}
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  )
}
