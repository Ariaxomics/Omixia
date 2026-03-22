import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { federationApi } from '../api/federation'
import LoadingSpinner from '../components/LoadingSpinner'
import Badge from '../components/Badge'

export default function FederationPage() {
  const qc = useQueryClient()
  const [labId, setLabId] = useState('')
  const [exportError, setExportError] = useState('')
  const [lastExport, setLastExport] = useState<Record<string, unknown> | null>(null)

  const { data: exports, isLoading: exportsLoading } = useQuery({
    queryKey: ['federation-exports'],
    queryFn: federationApi.listExports,
  })

  const { data: eligibleCount, isLoading: eligibleLoading } = useQuery({
    queryKey: ['federation-eligible'],
    queryFn: federationApi.eligibleCount,
  })

  const doExport = useMutation({
    mutationFn: () => federationApi.export(labId.trim()),
    onSuccess: (data) => {
      setLastExport(data)
      setExportError('')
      setLabId('')
      qc.invalidateQueries({ queryKey: ['federation-exports'] })
      qc.invalidateQueries({ queryKey: ['federation-eligible'] })
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
      setExportError(msg || 'Export failed')
    },
  })

  return (
    <div className="max-w-3xl">
      <h1 className="text-xl font-bold text-gray-900 mb-6">Federated Knowledge</h1>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-4 mb-8">
        <div className="bg-white border rounded-xl p-5">
          <p className="text-xs text-gray-500 mb-1">Eligible for export</p>
          <p className="text-3xl font-bold text-gray-900">
            {eligibleLoading ? '…' : (eligibleCount ?? 0)}
          </p>
          <p className="text-xs text-gray-400 mt-1">entries meeting eligibility criteria</p>
        </div>
        <div className="bg-white border rounded-xl p-5">
          <p className="text-xs text-gray-500 mb-1">Past exports</p>
          <p className="text-3xl font-bold text-gray-900">
            {exportsLoading ? '…' : (exports?.length ?? 0)}
          </p>
          <p className="text-xs text-gray-400 mt-1">export packages generated</p>
        </div>
      </div>

      {/* Export form */}
      <div className="bg-white border rounded-xl p-5 mb-8">
        <h2 className="font-semibold text-gray-900 mb-3">Generate export</h2>
        <p className="text-sm text-gray-500 mb-4">
          Exports eligible knowledge entries (observation_count ≥ 5, approved) for sharing with a
          federated registry.
        </p>
        <div className="flex gap-3">
          <input
            type="text"
            value={labId}
            onChange={(e) => setLabId(e.target.value)}
            placeholder="Lab ID (e.g. lab_london)"
            className="flex-1 border rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <button
            onClick={() => doExport.mutate()}
            disabled={doExport.isPending || !labId.trim()}
            className="px-5 py-2 bg-blue-600 text-white rounded text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            {doExport.isPending ? 'Exporting…' : 'Export'}
          </button>
        </div>
        {exportError && <p className="mt-2 text-sm text-red-600">{exportError}</p>}
        {lastExport && (
          <div className="mt-3 p-3 bg-green-50 rounded text-sm">
            <p className="font-medium text-green-800">Export created</p>
            <p className="text-green-700 text-xs mt-1">
              Lab: {lastExport.lab_id as string} · Entries: {lastExport.entry_count as number} ·
              Schema: {lastExport.schema_version as string}
            </p>
          </div>
        )}
      </div>

      {/* Exports table */}
      <div className="bg-white border rounded-xl overflow-hidden">
        <div className="px-5 py-3 border-b">
          <h2 className="font-semibold text-gray-900">Export history</h2>
        </div>
        {exportsLoading ? (
          <div className="p-6"><LoadingSpinner /></div>
        ) : (exports ?? []).length === 0 ? (
          <p className="text-gray-400 text-sm p-6">No exports yet.</p>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
              <tr>
                <th className="px-4 py-2 text-left">Lab ID</th>
                <th className="px-4 py-2 text-left">Entries</th>
                <th className="px-4 py-2 text-left">Schema</th>
                <th className="px-4 py-2 text-left">Status</th>
                <th className="px-4 py-2 text-left">Exported at</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {(exports ?? []).map((e, i) => (
                <tr key={i} className="hover:bg-gray-50">
                  <td className="px-4 py-2 font-mono text-xs">{e.lab_id as string}</td>
                  <td className="px-4 py-2">{e.entry_count as number}</td>
                  <td className="px-4 py-2 font-mono text-xs">{e.schema_version as string}</td>
                  <td className="px-4 py-2">
                    <Badge value={(e.status as string) || 'exported'} />
                  </td>
                  <td className="px-4 py-2 text-xs text-gray-500">
                    {e.exported_at ? new Date(e.exported_at as string).toLocaleString() : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
