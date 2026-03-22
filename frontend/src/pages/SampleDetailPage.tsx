import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { samplesApi } from '../api/samples'
import { variantsApi, ReviewPayload } from '../api/variants'
import { reportsApi } from '../api/reports'
import client from '../api/client'
import { useAuth } from '../contexts/AuthContext'
import LoadingSpinner from '../components/LoadingSpinner'
import Badge from '../components/Badge'

const TABS = ['SNVs', 'CNVs', 'SVs', 'Biomarkers', 'Preflight', 'Reports', 'Callsets'] as const
type Tab = typeof TABS[number]

export default function SampleDetailPage() {
  const { sampleId, assayId } = useParams<{ sampleId: string; assayId: string }>()
  const [activeTab, setActiveTab] = useState<Tab>('SNVs')

  const { data: summary } = useQuery({
    queryKey: ['summary', assayId],
    queryFn: () => samplesApi.getSummary(assayId!),
    enabled: !!assayId,
  })

  return (
    <div>
      {/* Header */}
      <div className="mb-5">
        <h1 className="text-xl font-bold text-gray-900">
          Assay: <span className="font-mono">{assayId}</span>
        </h1>
        <p className="text-gray-500 text-sm">Sample: {sampleId}</p>
      </div>

      {/* Summary */}
      {summary && (() => {
        const s = summary as Record<string, unknown>
        const raw = (s.raw_counts as Record<string, number>) ?? {}
        const rev = (s.review_counts as Record<string, number>) ?? {}
        const tiers = (s.tier_counts as Record<string, number>) ?? {}
        const stats: [string, string | number][] = [
          ['SNVs', raw.snv ?? 0],
          ['CNVs', raw.cnv ?? 0],
          ['SVs', raw.sv ?? 0],
          ['Reportable', rev.reportable ?? 0],
          ['Unreviewed', rev.unreviewed ?? 0],
          ['Tier 1', tiers.tier_1 ?? 0],
          ['Tier 2', tiers.tier_2 ?? 0],
          ['Tier 3', tiers.tier_3 ?? 0],
        ]
        return (
          <div className="grid grid-cols-4 sm:grid-cols-8 gap-3 mb-5">
            {stats.map(([label, val]) => (
              <div key={label} className="bg-white border rounded-lg px-4 py-3">
                <p className="text-xs text-gray-500">{label}</p>
                <p className="text-lg font-bold text-gray-900">{val}</p>
              </div>
            ))}
          </div>
        )
      })()}

      {/* Tabs */}
      <div className="border-b border-gray-200 mb-5">
        <nav className="flex gap-1">
          {TABS.map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              {tab}
            </button>
          ))}
        </nav>
      </div>

      {/* Tab Content */}
      {activeTab === 'SNVs' && <SnvsTab assayId={assayId!} />}
      {activeTab === 'CNVs' && <CnvsTab assayId={assayId!} />}
      {activeTab === 'SVs' && <SvsTab assayId={assayId!} />}
      {activeTab === 'Biomarkers' && <BiomarkersTab assayId={assayId!} />}
      {activeTab === 'Preflight' && <PreflightTab assayId={assayId!} />}
      {activeTab === 'Reports' && <ReportsTab assayId={assayId!} />}
      {activeTab === 'Callsets' && <CallsetsTab assayId={assayId!} />}
    </div>
  )
}

// Flatten review_current into the row so VariantTable can access review_status / tier directly
function flattenVariant(v: Record<string, unknown>): Record<string, unknown> {
  const rc = (v.review_current as Record<string, unknown>) ?? {}
  return { ...v, review_status: rc.status, tier: rc.tier }
}

// ── SNVs ─────────────────────────────────────────────────────────────────────

function SnvsTab({ assayId }: { assayId: string }) {
  const [selected, setSelected] = useState<Record<string, unknown> | null>(null)
  const { data, isLoading } = useQuery({
    queryKey: ['snvs', assayId],
    queryFn: async () => (await variantsApi.listSnvs(assayId)).map(flattenVariant),
  })

  if (isLoading) return <LoadingSpinner />
  return (
    <div className="flex gap-4">
      <div className="flex-1 overflow-auto">
        <VariantTable
          rows={data ?? []}
          columns={['gene', 'chrom', 'pos', 'ref', 'alt', 'hgvsp', 'vaf', 'review_status', 'tier']}
          onSelect={setSelected}
          selected={selected}
        />
      </div>
      {selected && (
        <ReviewPanel
          assayId={assayId}
          variant={selected}
          type="snv"
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  )
}

// ── CNVs ─────────────────────────────────────────────────────────────────────

function CnvsTab({ assayId }: { assayId: string }) {
  const [selected, setSelected] = useState<Record<string, unknown> | null>(null)
  const { data, isLoading } = useQuery({
    queryKey: ['cnvs', assayId],
    queryFn: async () => (await variantsApi.listCnvs(assayId)).map(flattenVariant),
  })

  if (isLoading) return <LoadingSpinner />
  return (
    <div className="flex gap-4">
      <div className="flex-1 overflow-auto">
        <VariantTable
          rows={data ?? []}
          columns={['gene', 'event_type', 'copy_number', 'review_status', 'tier']}
          onSelect={setSelected}
          selected={selected}
        />
      </div>
      {selected && (
        <ReviewPanel
          assayId={assayId}
          variant={selected}
          type="cnv"
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  )
}

// ── SVs ───────────────────────────────────────────────────────────────────────

function SvsTab({ assayId }: { assayId: string }) {
  const [selected, setSelected] = useState<Record<string, unknown> | null>(null)
  const { data, isLoading } = useQuery({
    queryKey: ['svs', assayId],
    queryFn: async () => (await variantsApi.listSvs(assayId)).map(flattenVariant),
  })

  if (isLoading) return <LoadingSpinner />
  return (
    <div className="flex gap-4">
      <div className="flex-1 overflow-auto">
        <VariantTable
          rows={data ?? []}
          columns={['sv_type', 'gene_5prime', 'gene_3prime', 'review_status', 'tier']}
          onSelect={setSelected}
          selected={selected}
        />
      </div>
      {selected && (
        <ReviewPanel
          assayId={assayId}
          variant={selected}
          type="sv"
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  )
}

// ── Shared VariantTable ───────────────────────────────────────────────────────

function VariantTable({
  rows,
  columns,
  onSelect,
  selected,
}: {
  rows: Record<string, unknown>[]
  columns: string[]
  onSelect: (row: Record<string, unknown>) => void
  selected: Record<string, unknown> | null
}) {
  if (rows.length === 0) return <p className="text-gray-400 py-6 text-sm">No variants.</p>
  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-auto">
      <table className="w-full text-sm">
        <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
          <tr>
            {columns.map((c) => (
              <th key={c} className="px-3 py-2 text-left whitespace-nowrap">
                {c.replace(/_/g, ' ')}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {rows.map((row, i) => {
            const isSelected = selected === row
            return (
              <tr
                key={i}
                onClick={() => onSelect(row)}
                className={`cursor-pointer transition-colors ${
                  isSelected ? 'bg-blue-50' : 'hover:bg-gray-50'
                }`}
              >
                {columns.map((c) => (
                  <td key={c} className="px-3 py-2 whitespace-nowrap">
                    {c === 'review_status' || c === 'tier' ? (
                      <Badge value={(row[c] as string) || ''} type={c === 'tier' ? 'tier' : 'status'} />
                    ) : (
                      <span className="font-mono text-xs">{String(row[c] ?? '—')}</span>
                    )}
                  </td>
                ))}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// ── ReviewPanel ───────────────────────────────────────────────────────────────

function ReviewPanel({
  assayId,
  variant,
  type,
  onClose,
}: {
  assayId: string
  variant: Record<string, unknown>
  type: 'snv' | 'cnv' | 'sv'
  onClose: () => void
}) {
  const qc = useQueryClient()
  const [tier, setTier] = useState<string>((variant.tier as string) || '')
  const [isArtifact, setIsArtifact] = useState<boolean>((variant.is_artifact as boolean) || false)
  const [interpretation, setInterpretation] = useState<string>((variant.interpretation as string) || '')
  const [note, setNote] = useState('')
  const [error, setError] = useState('')

  const mutation = useMutation({
    mutationFn: (payload: ReviewPayload) => {
      if (type === 'snv') {
        return variantsApi.reviewSnv(
          assayId,
          variant.chrom as string,
          variant.pos as string,
          variant.ref as string,
          variant.alt as string,
          payload,
        )
      } else if (type === 'cnv') {
        return variantsApi.reviewCnv(assayId, variant.gene as string, payload)
      } else {
        return variantsApi.reviewSv(assayId, variant.sv_id as string, payload)
      }
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [type === 'snv' ? 'snvs' : type === 'cnv' ? 'cnvs' : 'svs', assayId] })
      qc.invalidateQueries({ queryKey: ['summary', assayId] })
      setError('')
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
      setError(msg || 'Review failed')
    },
  })

  return (
    <div className="w-80 shrink-0 bg-white border border-gray-200 rounded-xl p-4 h-fit">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold text-gray-900 text-sm">Review</h3>
        <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-lg leading-none">×</button>
      </div>

      {/* Variant info */}
      <div className="bg-gray-50 rounded-lg p-3 mb-3 text-xs space-y-1 font-mono">
        {Object.entries(variant)
          .filter(([k]) => !k.startsWith('_') && !['review_history', 'interpretation'].includes(k))
          .slice(0, 6)
          .map(([k, v]) => (
            <div key={k} className="flex justify-between gap-2">
              <span className="text-gray-500">{k}</span>
              <span className="text-gray-900 truncate">{String(v ?? '—')}</span>
            </div>
          ))}
      </div>

      <div className="space-y-3">
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">Tier</label>
          <select
            value={tier}
            onChange={(e) => setTier(e.target.value)}
            className="w-full border rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">— No tier —</option>
            <option value="tier_1">Tier 1 (Strong clinical significance)</option>
            <option value="tier_2">Tier 2 (Potential clinical significance)</option>
            <option value="tier_3">Tier 3 (Unknown significance)</option>
            <option value="tier_4">Tier 4 (Benign)</option>
          </select>
        </div>

        <div className="flex items-center gap-2">
          <input
            type="checkbox"
            id="artifact"
            checked={isArtifact}
            onChange={(e) => setIsArtifact(e.target.checked)}
            className="rounded"
          />
          <label htmlFor="artifact" className="text-sm text-gray-700">Mark as artifact</label>
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">Interpretation</label>
          <textarea
            value={interpretation}
            onChange={(e) => setInterpretation(e.target.value)}
            rows={3}
            className="w-full border rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
            placeholder="Clinical interpretation…"
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">Note</label>
          <input
            type="text"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            className="w-full border rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="Optional note…"
          />
        </div>

        {error && <p className="text-xs text-red-600 bg-red-50 px-2 py-1.5 rounded">{error}</p>}

        <button
          onClick={() =>
            mutation.mutate({
              tier: tier || null,
              is_artifact: isArtifact,
              interpretation,
              note,
            })
          }
          disabled={mutation.isPending}
          className="w-full bg-blue-600 text-white py-1.5 rounded text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          {mutation.isPending ? 'Submitting…' : 'Submit Review'}
        </button>
        {mutation.isSuccess && (
          <p className="text-xs text-green-600 text-center">Review submitted</p>
        )}
      </div>
    </div>
  )
}

// ── Biomarkers ────────────────────────────────────────────────────────────────

function BiomarkersTab({ assayId }: { assayId: string }) {
  const qc = useQueryClient()
  const [note, setNote] = useState('')
  const [ack, setAck] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['biomarkers', assayId],
    queryFn: () => variantsApi.getBiomarkers(assayId),
  })

  const confirm = useMutation({
    mutationFn: () =>
      variantsApi.confirmBiomarkers(assayId, { reviewer_note: note, discordance_acknowledged: ack }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['biomarkers', assayId] }),
  })

  if (isLoading) return <LoadingSpinner />
  if (!data) return <p className="text-gray-400 py-6 text-sm">No biomarker data.</p>

  const bm = data as Record<string, unknown>
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 max-w-2xl">
      <h2 className="font-semibold text-gray-900 mb-3">Biomarkers</h2>
      <div className="grid grid-cols-2 gap-3 mb-4">
        {(['msi_classification', 'msi_score', 'tmb_classification', 'tmb_mut_per_mb', 'review_status'] as const).map((k) => (
          <div key={k} className="bg-gray-50 rounded p-3">
            <p className="text-xs text-gray-500 capitalize">{k.replace(/_/g, ' ')}</p>
            <p className="font-semibold text-gray-900">{String(bm[k] ?? '—')}</p>
          </div>
        ))}
        {(bm.discordance_flag as boolean) && (
          <div className="col-span-2 bg-amber-50 border border-amber-200 rounded p-3">
            <p className="text-xs font-medium text-amber-800 mb-1">Discordance flag</p>
            <p className="text-xs text-amber-700">{bm.discordance_note as string}</p>
          </div>
        )}
      </div>

      {bm.review_status !== 'confirmed' && (
        <div className="space-y-3 border-t pt-4">
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={2}
            placeholder="Reviewer note…"
            className="w-full border rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <label className="flex items-center gap-2 text-sm text-gray-700">
            <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
            Acknowledge discordance
          </label>
          <button
            onClick={() => confirm.mutate()}
            disabled={confirm.isPending}
            className="px-4 py-1.5 bg-blue-600 text-white rounded text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
          >
            {confirm.isPending ? 'Confirming…' : 'Confirm Biomarkers'}
          </button>
        </div>
      )}
    </div>
  )
}

// ── Preflight ─────────────────────────────────────────────────────────────────

function PreflightTab({ assayId }: { assayId: string }) {
  const { data, isLoading, refetch } = useQuery({
    queryKey: ['preflight', assayId],
    queryFn: () => variantsApi.preflight(assayId),
  })

  if (isLoading) return <LoadingSpinner />

  const checks = (data?.data ?? []) as Record<string, unknown>[]
  const allPassed = data?.all_passed

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 max-w-2xl">
      <div className="flex items-center justify-between mb-4">
        <h2 className="font-semibold text-gray-900">Preflight Checks</h2>
        <button onClick={() => refetch()} className="text-sm text-blue-600 hover:underline">
          Re-run
        </button>
      </div>
      <div
        className={`mb-4 px-4 py-2 rounded-lg text-sm font-medium ${
          allPassed ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
        }`}
      >
        {allPassed ? 'All checks passed' : 'Some checks failed'}
      </div>
      <div className="space-y-2">
        {checks.map((check, i) => {
          const passed = (check.status as string) === 'pass'
          return (
            <div
              key={i}
              className={`flex items-start gap-3 px-4 py-3 rounded-lg ${
                passed ? 'bg-green-50' : 'bg-red-50'
              }`}
            >
              <span className={`text-lg ${passed ? 'text-green-500' : 'text-red-500'}`}>
                {passed ? '✓' : '✗'}
              </span>
              <div>
                <p className="text-sm font-medium text-gray-900">{check.description as string}</p>
                {(check.detail as string) && (
                  <p className="text-xs text-gray-600 mt-0.5">{check.detail as string}</p>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Reports ───────────────────────────────────────────────────────────────────

function ReportsTab({ assayId }: { assayId: string }) {
  const qc = useQueryClient()
  const { user } = useAuth()
  const [error, setError] = useState('')
  const [tokenResults, setTokenResults] = useState<Record<string, string>>({})
  const [tokenErrors, setTokenErrors] = useState<Record<string, string>>({})

  const { data: reports, isLoading } = useQuery({
    queryKey: ['reports', assayId],
    queryFn: () => reportsApi.list(assayId),
  })

  const create = useMutation({
    mutationFn: () => reportsApi.create(assayId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['reports', assayId] })
      setError('')
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
      setError(msg || 'Failed to create report')
    },
  })

  const signOff = useMutation({
    mutationFn: (reportId: string) => reportsApi.signOff(reportId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['reports', assayId] }),
  })

  const finalise = useMutation({
    mutationFn: (reportId: string) => reportsApi.finalise(reportId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['reports', assayId] }),
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
      setError(msg || 'Failed to finalise report')
    },
  })

  const issueToken = async (reportId: string) => {
    try {
      const result = await reportsApi.issuePortalToken(reportId)
      setTokenResults((prev) => ({ ...prev, [reportId]: result.portal_url }))
      setTokenErrors((prev) => { const n = { ...prev }; delete n[reportId]; return n })
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
      setTokenErrors((prev) => ({ ...prev, [reportId]: msg || 'Failed to issue token' }))
    }
  }

  const canIssueToken = ['lab_director', 'senior_reviewer', 'admin'].includes(user?.role ?? '')
  const exportBase = client.defaults.baseURL ?? '/api'

  if (isLoading) return <LoadingSpinner />

  return (
    <div className="max-w-2xl">
      <div className="flex items-center justify-between mb-4">
        <h2 className="font-semibold text-gray-900">Reports</h2>
        <button
          onClick={() => create.mutate()}
          disabled={create.isPending}
          className="px-4 py-1.5 bg-blue-600 text-white rounded text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
        >
          {create.isPending ? 'Creating…' : '+ New Draft'}
        </button>
      </div>
      {error && <p className="text-sm text-red-600 mb-3">{error}</p>}
      {(reports ?? []).length === 0 ? (
        <p className="text-gray-400 text-sm py-6">No reports yet.</p>
      ) : (
        <div className="space-y-3">
          {(reports ?? []).map((r: Record<string, unknown>) => (
            <div key={r.report_id as string} className="bg-white border border-gray-200 rounded-xl p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="font-mono text-xs text-gray-500">{r.report_id as string}</span>
                <Badge value={r.status as string} />
              </div>
              <p className="text-sm text-gray-600 mb-3">
                Created by {r.created_by_username as string} · Sign-offs:{' '}
                {(r.sign_offs as unknown[])?.length ?? 0}
              </p>
              <div className="flex gap-2 flex-wrap">
                {r.status !== 'finalised' && (
                  <button
                    onClick={() => signOff.mutate(r.report_id as string)}
                    className="px-3 py-1 text-xs bg-gray-100 hover:bg-gray-200 rounded font-medium transition-colors"
                  >
                    Sign off
                  </button>
                )}
                {(r.status === 'pending_sign_off' || r.status === 'draft') && (
                  <button
                    onClick={() => finalise.mutate(r.report_id as string)}
                    className="px-3 py-1 text-xs bg-green-100 hover:bg-green-200 text-green-800 rounded font-medium transition-colors"
                  >
                    Finalise
                  </button>
                )}
                <a
                  href={`${exportBase}/reports/${r.report_id as string}/export`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="px-3 py-1 text-xs bg-blue-50 hover:bg-blue-100 text-blue-700 rounded font-medium transition-colors"
                >
                  Export JSON
                </a>
                {canIssueToken && r.status === 'finalised' && (
                  <button
                    onClick={() => issueToken(r.report_id as string)}
                    className="px-3 py-1 text-xs bg-purple-50 hover:bg-purple-100 text-purple-700 rounded font-medium transition-colors"
                  >
                    Issue physician link
                  </button>
                )}
              </div>
              {tokenResults[r.report_id as string] && (
                <div className="mt-3 p-2 bg-purple-50 rounded text-xs">
                  <p className="text-purple-700 font-medium mb-1">Physician access link:</p>
                  <code className="break-all text-purple-900">{tokenResults[r.report_id as string]}</code>
                </div>
              )}
              {tokenErrors[r.report_id as string] && (
                <p className="mt-2 text-xs text-red-600">{tokenErrors[r.report_id as string]}</p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Callsets ──────────────────────────────────────────────────────────────────

function CallsetsTab({ assayId }: { assayId: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ['callsets', assayId],
    queryFn: () => variantsApi.listCallsets(assayId),
  })

  if (isLoading) return <LoadingSpinner />
  if (!data || data.length === 0)
    return <p className="text-gray-400 py-6 text-sm">No callsets imported.</p>

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden max-w-3xl">
      <table className="w-full text-sm">
        <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
          <tr>
            <th className="px-4 py-2 text-left">Callset ID</th>
            <th className="px-4 py-2 text-left">Status</th>
            <th className="px-4 py-2 text-left">SNVs</th>
            <th className="px-4 py-2 text-left">CNVs</th>
            <th className="px-4 py-2 text-left">SVs</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {data.map((c: Record<string, unknown>) => {
            const counts = (c.raw_counts as Record<string, number>) ?? {}
            return (
              <tr key={c.callset_id as string}>
                <td className="px-4 py-2 font-mono text-xs">{c.callset_id as string}</td>
                <td className="px-4 py-2"><Badge value={c.is_active ? 'active' : 'inactive'} /></td>
                <td className="px-4 py-2">{counts.snv ?? '—'}</td>
                <td className="px-4 py-2">{counts.cnv ?? '—'}</td>
                <td className="px-4 py-2">{counts.sv ?? '—'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
