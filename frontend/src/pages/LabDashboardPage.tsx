import { useQuery } from '@tanstack/react-query'
import { labApi } from '../api/lab'
import { useAuth } from '../contexts/AuthContext'
import LoadingSpinner from '../components/LoadingSpinner'

const ALLOWED_ROLES = ['admin', 'lab_director', 'senior_reviewer']

interface ActiveCase {
  sample_assay_id: string
  sample_id: string
  assay_id: string
  status: string
  priority: string
  sla_due_at: string | null
  _sla_status: string
  _is_stalled: boolean
  _tat_hours: number | null
}

interface AssayBreakdown {
  assay_id: string
  count: number
  median_tat_hours: number
}

interface DashboardStats {
  total_active: number
  total_finalised: number
  breached_count: number
  amber_count: number
  stalled_count: number
  pct_within_sla: number | null
  median_tat_hours: number | null
  active_cases: ActiveCase[]
  assay_breakdown: AssayBreakdown[]
}

const SLA_BADGE: Record<string, string> = {
  breached: 'bg-red-100 text-red-700 border border-red-200',
  amber: 'bg-amber-100 text-amber-700 border border-amber-200',
  on_track: 'bg-green-100 text-green-700 border border-green-200',
  unknown: 'bg-gray-100 text-gray-500 border border-gray-200',
  complete: 'bg-blue-100 text-blue-600 border border-blue-200',
}

const SLA_LABEL: Record<string, string> = {
  breached: 'Breached',
  amber: 'Due soon',
  on_track: 'On track',
  unknown: 'No SLA',
  complete: 'Complete',
}

const STATUS_LABEL: Record<string, string> = {
  pending_qc: 'Pending QC',
  analysis_ready: 'Analysis ready',
  review_in_progress: 'In review',
  review_complete: 'Review complete',
  preflight_failed: 'Preflight failed',
  finalised: 'Finalised',
  report_delivered: 'Delivered',
}

function StatCard({ label, value, sub, colour }: { label: string; value: string | number; sub?: string; colour?: string }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 px-5 py-4">
      <p className="text-xs text-gray-500 uppercase tracking-wide font-medium">{label}</p>
      <p className={`text-3xl font-bold mt-1 ${colour ?? 'text-gray-900'}`}>{value}</p>
      {sub && <p className="text-xs text-gray-400 mt-0.5">{sub}</p>}
    </div>
  )
}

function formatDate(iso: string | null) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
}

export default function LabDashboardPage() {
  const { user } = useAuth()
  const allowed = ALLOWED_ROLES.includes(user?.role ?? '')

  const { data, isLoading, error } = useQuery({
    queryKey: ['lab-dashboard'],
    queryFn: labApi.dashboard,
    enabled: allowed,
  })

  if (!allowed) {
    return <div className="text-center py-20 text-gray-400">Access restricted to Lab Director / Senior Reviewer / Admin</div>
  }

  if (isLoading) return <LoadingSpinner />

  if (error) {
    return <div className="text-center py-20 text-red-500 text-sm">Failed to load dashboard data</div>
  }

  const stats = data as DashboardStats | undefined
  if (!stats) return null

  return (
    <div className="space-y-8">
      <h1 className="text-2xl font-bold text-gray-900">Lab Dashboard</h1>

      {/* Summary stat cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
        <StatCard label="Active Cases" value={stats.total_active} />
        <StatCard label="Finalised" value={stats.total_finalised} />
        <StatCard
          label="SLA Breached"
          value={stats.breached_count}
          colour={stats.breached_count > 0 ? 'text-red-600' : 'text-gray-900'}
        />
        <StatCard
          label="Due Within 48h"
          value={stats.amber_count}
          colour={stats.amber_count > 0 ? 'text-amber-600' : 'text-gray-900'}
        />
        <StatCard
          label="Stalled Cases"
          value={stats.stalled_count}
          sub="No activity >24h"
          colour={stats.stalled_count > 0 ? 'text-orange-600' : 'text-gray-900'}
        />
        <StatCard
          label="Within SLA"
          value={stats.pct_within_sla !== null ? `${stats.pct_within_sla}%` : '—'}
          sub="Of finalised cases"
        />
        <StatCard
          label="Median TAT"
          value={stats.median_tat_hours !== null ? `${stats.median_tat_hours}h` : '—'}
          sub="Finalised cases"
        />
      </div>

      {/* Active cases table */}
      <div>
        <h2 className="text-lg font-semibold text-gray-800 mb-3">Active Cases</h2>
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          {stats.active_cases.length === 0 ? (
            <div className="py-12 text-center text-gray-400 text-sm">No active cases</div>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b">
                <tr>
                  <th className="px-4 py-3 text-left font-medium text-gray-600">Case</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-600">Assay</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-600">Status</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-600">Priority</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-600">SLA Due</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-600">SLA</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-600">TAT</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-600"></th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {stats.active_cases.map((c) => (
                  <tr key={c.sample_assay_id} className="hover:bg-gray-50 transition-colors">
                    <td className="px-4 py-3">
                      <p className="font-medium text-gray-900">{c.sample_id}</p>
                      <p className="text-xs text-gray-400">{c.sample_assay_id}</p>
                    </td>
                    <td className="px-4 py-3 text-gray-600">{c.assay_id}</td>
                    <td className="px-4 py-3 text-gray-600">{STATUS_LABEL[c.status] ?? c.status}</td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-0.5 rounded text-xs font-medium capitalize ${
                        c.priority === 'urgent' ? 'bg-red-50 text-red-600' : 'bg-gray-100 text-gray-600'
                      }`}>
                        {c.priority}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-600">{formatDate(c.sla_due_at)}</td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${SLA_BADGE[c._sla_status] ?? ''}`}>
                        {SLA_LABEL[c._sla_status] ?? c._sla_status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-600">
                      {c._tat_hours !== null ? `${c._tat_hours}h` : '—'}
                    </td>
                    <td className="px-4 py-3">
                      {c._is_stalled && (
                        <span className="px-2 py-0.5 rounded text-xs font-medium bg-orange-100 text-orange-700">
                          Stalled
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Per-assay TAT breakdown */}
      {stats.assay_breakdown.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold text-gray-800 mb-3">TAT by Assay (Finalised)</h2>
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b">
                <tr>
                  <th className="px-4 py-3 text-left font-medium text-gray-600">Assay</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-600">Cases</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-600">Median TAT</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {stats.assay_breakdown.map((b) => (
                  <tr key={b.assay_id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 font-medium text-gray-900">{b.assay_id}</td>
                    <td className="px-4 py-3 text-gray-600">{b.count}</td>
                    <td className="px-4 py-3 text-gray-600">{b.median_tat_hours}h</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
