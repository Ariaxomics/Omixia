import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { knowledgeApi, KnowledgePayload } from '../api/knowledge'
import { useAuth } from '../contexts/AuthContext'
import LoadingSpinner from '../components/LoadingSpinner'
import Badge from '../components/Badge'

const VARIANT_TYPES = ['snv', 'cnv', 'sv', 'fusion', 'biomarker']
const TIERS = ['tier_1', 'tier_2', 'tier_3', 'tier_4']

export default function KnowledgePage() {
  const { user } = useAuth()
  const qc = useQueryClient()
  const [search, setSearch] = useState('')
  const [geneFilter, setGeneFilter] = useState('')
  const [tierFilter, setTierFilter] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [selected, setSelected] = useState<Record<string, unknown> | null>(null)

  const canEdit = user?.role === 'lab_director' || user?.role === 'senior_reviewer'

  const searchWords = search.trim().split(/\s+/).filter(Boolean).length
  const searchTooShort = search.trim().length > 0 && searchWords < 3

  const { data, isLoading, isError } = useQuery({
    queryKey: ['knowledge', { search, gene: geneFilter, tier: tierFilter }],
    queryFn: () =>
      search.trim()
        ? knowledgeApi.search(search, { gene: geneFilter, tier: tierFilter })
        : knowledgeApi.list({ gene: geneFilter, tier: tierFilter }),
    enabled: !searchTooShort,
    retry: false,
  })

  const createMut = useMutation({
    mutationFn: (payload: KnowledgePayload) => knowledgeApi.create(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['knowledge'] })
      setShowCreate(false)
    },
  })

  return (
    <div>
      <div className="mb-5 flex items-center justify-between">
        <h1 className="text-xl font-bold text-gray-900">Knowledge Database</h1>
        {canEdit && (
          <button
            onClick={() => setShowCreate(true)}
            className="px-4 py-1.5 bg-blue-600 text-white rounded text-sm font-medium hover:bg-blue-700"
          >
            + New Entry
          </button>
        )}
      </div>

      {/* Filters */}
      <div className="flex gap-3 mb-1">
        <input
          type="text"
          placeholder="Full-text search (3+ words)…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="border rounded-lg px-3 py-1.5 text-sm w-56 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <input
          type="text"
          placeholder="Gene filter…"
          value={geneFilter}
          onChange={(e) => setGeneFilter(e.target.value)}
          className="border rounded-lg px-3 py-1.5 text-sm w-36 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <select
          value={tierFilter}
          onChange={(e) => setTierFilter(e.target.value)}
          className="border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="">All tiers</option>
          {TIERS.map((t) => <option key={t} value={t}>{t.replace('_', ' ')}</option>)}
        </select>
      </div>
      {searchTooShort && (
        <p className="text-xs text-amber-600 mb-4">Full-text search requires at least 3 words. Use the Gene filter for single-gene lookup.</p>
      )}
      {isError && !searchTooShort && (
        <p className="text-xs text-red-600 mb-4">Search failed. Try different terms.</p>
      )}

      <div className="flex gap-4 mt-4">
        {/* List */}
        <div className="flex-1">
          {isLoading ? (
            <LoadingSpinner />
          ) : (
            <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
                  <tr>
                    <th className="px-4 py-2 text-left">Gene</th>
                    <th className="px-4 py-2 text-left">Type</th>
                    <th className="px-4 py-2 text-left">HGVSp</th>
                    <th className="px-4 py-2 text-left">Disease</th>
                    <th className="px-4 py-2 text-left">Tier</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {(data ?? []).map((e: Record<string, unknown>) => (
                    <tr
                      key={e.knowledge_id as string}
                      onClick={() => setSelected(e)}
                      className={`cursor-pointer transition-colors ${
                        selected?.knowledge_id === e.knowledge_id ? 'bg-blue-50' : 'hover:bg-gray-50'
                      }`}
                    >
                      <td className="px-4 py-2 font-semibold">{e.gene as string}</td>
                      <td className="px-4 py-2 text-gray-500">{e.variant_type as string}</td>
                      <td className="px-4 py-2 font-mono text-xs">{(e.hgvsp as string) || '—'}</td>
                      <td className="px-4 py-2 text-gray-500">{(e.disease_subtype as string) || (e.disease_group as string) || '—'}</td>
                      <td className="px-4 py-2">
                        <Badge value={e.tier as string} type="tier" />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {(data ?? []).length === 0 && (
                <p className="text-center text-gray-400 py-8 text-sm">No entries found</p>
              )}
            </div>
          )}
        </div>

        {/* Detail panel */}
        {selected && (
          <KnowledgeDetail
            entry={selected}
            canEdit={canEdit}
            onClose={() => setSelected(null)}
            onUpdated={() => {
              qc.invalidateQueries({ queryKey: ['knowledge'] })
              setSelected(null)
            }}
          />
        )}
      </div>

      {/* Create modal */}
      {showCreate && (
        <KnowledgeForm
          onSubmit={(payload) => createMut.mutate(payload)}
          onClose={() => setShowCreate(false)}
          loading={createMut.isPending}
          error={(createMut.error as { response?: { data?: { error?: string } } })?.response?.data?.error}
        />
      )}
    </div>
  )
}

function KnowledgeDetail({
  entry,
  canEdit,
  onClose,
  onUpdated,
}: {
  entry: Record<string, unknown>
  canEdit: boolean
  onClose: () => void
  onUpdated: () => void
}) {
  const [editing, setEditing] = useState(false)
  const updateMut = useMutation({
    mutationFn: (payload: Partial<KnowledgePayload>) =>
      knowledgeApi.update(entry.knowledge_id as string, payload),
    onSuccess: () => {
      setEditing(false)
      onUpdated()
    },
  })

  return (
    <div className="w-80 shrink-0 bg-white border border-gray-200 rounded-xl p-4 h-fit">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold text-gray-900 text-sm">Knowledge Entry</h3>
        <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-lg leading-none">×</button>
      </div>

      {!editing ? (
        <>
          <div className="space-y-2 text-sm">
            <Row label="Gene" value={entry.gene as string} />
            <Row label="Type" value={entry.variant_type as string} />
            <Row label="HGVSp" value={entry.hgvsp as string} />
            <Row label="Tier" value={<Badge value={entry.tier as string} type="tier" />} />
            <Row label="Disease" value={(entry.disease_subtype as string) || (entry.disease_group as string)} />
            <div>
              <p className="text-xs text-gray-500 mb-1">Interpretation</p>
              <p className="text-gray-900">{entry.interpretation as string}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500 mb-1">Evidence Summary</p>
              <p className="text-gray-900 text-xs">{entry.evidence_summary as string}</p>
            </div>
          </div>
          {canEdit && (
            <button
              onClick={() => setEditing(true)}
              className="mt-4 w-full px-3 py-1.5 text-sm bg-gray-100 hover:bg-gray-200 rounded font-medium"
            >
              Edit
            </button>
          )}
        </>
      ) : (
        <KnowledgeForm
          initial={entry}
          onSubmit={(payload) => updateMut.mutate(payload)}
          onClose={() => setEditing(false)}
          loading={updateMut.isPending}
          inline
        />
      )}
    </div>
  )
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-2">
      <span className="text-xs text-gray-500">{label}</span>
      <span className="text-gray-900 text-xs font-medium">{value || '—'}</span>
    </div>
  )
}

function KnowledgeForm({
  initial,
  onSubmit,
  onClose,
  loading,
  error,
  inline = false,
}: {
  initial?: Record<string, unknown>
  onSubmit: (payload: KnowledgePayload) => void
  onClose: () => void
  loading: boolean
  error?: string
  inline?: boolean
}) {
  const [form, setForm] = useState<Partial<KnowledgePayload>>({
    gene: (initial?.gene as string) || '',
    variant_type: (initial?.variant_type as string) || 'snv',
    hgvsp: (initial?.hgvsp as string) || '',
    tier: (initial?.tier as string) || 'tier_3',
    disease_group: (initial?.disease_group as string) || '',
    disease_subtype: (initial?.disease_subtype as string) || '',
    interpretation: (initial?.interpretation as string) || '',
    evidence_summary: (initial?.evidence_summary as string) || '',
  })

  const set = (k: keyof KnowledgePayload) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    setForm((p) => ({ ...p, [k]: e.target.value }))

  const content = (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="text-xs font-medium text-gray-700">Gene *</label>
          <input value={form.gene} onChange={set('gene')} className="w-full border rounded px-2 py-1.5 text-sm mt-0.5" />
        </div>
        <div>
          <label className="text-xs font-medium text-gray-700">Type *</label>
          <select value={form.variant_type} onChange={set('variant_type')} className="w-full border rounded px-2 py-1.5 text-sm mt-0.5">
            {VARIANT_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
      </div>
      <div>
        <label className="text-xs font-medium text-gray-700">HGVSp</label>
        <input value={form.hgvsp} onChange={set('hgvsp')} className="w-full border rounded px-2 py-1.5 text-sm mt-0.5" />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="text-xs font-medium text-gray-700">Tier *</label>
          <select value={form.tier} onChange={set('tier')} className="w-full border rounded px-2 py-1.5 text-sm mt-0.5">
            {TIERS.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
        <div>
          <label className="text-xs font-medium text-gray-700">Disease Group *</label>
          <input value={form.disease_group} onChange={set('disease_group')} className="w-full border rounded px-2 py-1.5 text-sm mt-0.5" />
        </div>
      </div>
      <div>
        <label className="text-xs font-medium text-gray-700">Interpretation *</label>
        <input value={form.interpretation} onChange={set('interpretation')} className="w-full border rounded px-2 py-1.5 text-sm mt-0.5" />
      </div>
      <div>
        <label className="text-xs font-medium text-gray-700">Evidence Summary *</label>
        <textarea value={form.evidence_summary} onChange={set('evidence_summary')} rows={3} className="w-full border rounded px-2 py-1.5 text-sm mt-0.5 resize-none" />
      </div>
      {error && <p className="text-xs text-red-600">{error}</p>}
      <div className="flex gap-2">
        <button
          onClick={() => onSubmit(form as KnowledgePayload)}
          disabled={loading}
          className="flex-1 bg-blue-600 text-white py-1.5 rounded text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? 'Saving…' : initial ? 'Update' : 'Create'}
        </button>
        <button onClick={onClose} className="px-3 py-1.5 border rounded text-sm hover:bg-gray-50">
          Cancel
        </button>
      </div>
    </div>
  )

  if (inline) return content

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-semibold text-gray-900">New Knowledge Entry</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none">×</button>
        </div>
        {content}
      </div>
    </div>
  )
}
