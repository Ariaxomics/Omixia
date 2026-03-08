import { useQuery } from '@tanstack/react-query'
import { labApi } from '../api/lab'
import { useAuth } from '../contexts/AuthContext'
import LoadingSpinner from '../components/LoadingSpinner'

export default function LabDashboardPage() {
  const { user } = useAuth()
  const allowed = user?.role === 'lab_director' || user?.role === 'senior_reviewer'

  const { data, isLoading } = useQuery({
    queryKey: ['lab-dashboard'],
    queryFn: labApi.dashboard,
    enabled: allowed,
  })

  if (!allowed) {
    return <div className="text-center py-20 text-gray-400">Access restricted to Lab Director / Senior Reviewer</div>
  }

  if (isLoading) return <LoadingSpinner />

  const stats = data as Record<string, unknown> | undefined

  return (
    <div>
      <h1 className="text-xl font-bold text-gray-900 mb-6">Lab Dashboard</h1>
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
          {Object.entries(stats)
            .filter(([k]) => !k.startsWith('_'))
            .map(([k, v]) => (
              <div key={k} className="bg-white rounded-xl border border-gray-200 px-5 py-4">
                <p className="text-xs text-gray-500 uppercase tracking-wide capitalize">
                  {k.replace(/_/g, ' ')}
                </p>
                <p className="text-2xl font-bold text-gray-900 mt-1">
                  {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                </p>
              </div>
            ))}
        </div>
      )}
    </div>
  )
}
