import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { samplesApi } from '../api/samples'
import { useAuth } from '../contexts/AuthContext'
import LoadingSpinner from '../components/LoadingSpinner'
import Badge from '../components/Badge'

export default function DashboardPage() {
  const { user } = useAuth()
  const { data: samples, isLoading } = useQuery({
    queryKey: ['samples'],
    queryFn: samplesApi.list,
  })

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">
          Welcome, {user?.full_name || user?.username}
        </h1>
        <p className="text-gray-500 text-sm mt-1">Omixia Genomic Variant Review</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
        <StatCard label="Total Samples" value={samples?.length ?? '—'} />
        <StatCard label="Your Role" value={user?.role?.replace(/_/g, ' ') ?? '—'} />
        <StatCard label="Platform" value="Omixia v1" />
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-gray-200">
        <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
          <h2 className="font-semibold text-gray-900">Recent Samples</h2>
          <Link to="/samples" className="text-sm text-blue-600 hover:underline">View all →</Link>
        </div>
        {isLoading ? (
          <LoadingSpinner />
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
              <tr>
                <th className="px-4 py-3 text-left">Sample ID</th>
                <th className="px-4 py-3 text-left">Patient</th>
                <th className="px-4 py-3 text-left">Disease</th>
                <th className="px-4 py-3 text-left">Status</th>
                <th className="px-4 py-3 text-left"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {(samples ?? []).slice(0, 10).map((s: Record<string, unknown>) => (
                <tr key={s._id as string} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-mono text-xs">{s.sample_id as string}</td>
                  <td className="px-4 py-3">{s.patient_name as string || '—'}</td>
                  <td className="px-4 py-3 text-gray-600">{s.disease_subtype as string || s.disease_group as string || '—'}</td>
                  <td className="px-4 py-3">
                    <Badge value={(s.status as string) || 'unreviewed'} />
                  </td>
                  <td className="px-4 py-3">
                    <Link
                      to={`/samples`}
                      className="text-blue-600 hover:underline text-xs"
                    >
                      View
                    </Link>
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

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 px-5 py-4">
      <p className="text-xs text-gray-500 uppercase tracking-wide">{label}</p>
      <p className="text-2xl font-bold text-gray-900 mt-1 capitalize">{value}</p>
    </div>
  )
}
