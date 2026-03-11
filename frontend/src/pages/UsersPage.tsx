import { useState, FormEvent } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '../contexts/AuthContext'
import { usersApi, CreateUserPayload } from '../api/users'

// Roles each actor is allowed to assign
const ROLES_BY_ACTOR: Record<string, string[]> = {
  admin: ['admin', 'lab_director', 'senior_reviewer', 'bioinformatician', 'reviewer', 'ordering_physician'],
  lab_director: ['senior_reviewer', 'bioinformatician', 'reviewer', 'ordering_physician'],
}

const ROLE_LABELS: Record<string, string> = {
  admin: 'Admin',
  lab_director: 'Lab Director',
  senior_reviewer: 'Senior Reviewer',
  bioinformatician: 'Bioinformatician',
  reviewer: 'Reviewer',
  ordering_physician: 'Ordering Physician',
}

const ROLE_BADGE_COLOURS: Record<string, string> = {
  admin: 'bg-red-100 text-red-700',
  lab_director: 'bg-purple-100 text-purple-700',
  senior_reviewer: 'bg-blue-100 text-blue-700',
  bioinformatician: 'bg-teal-100 text-teal-700',
  reviewer: 'bg-green-100 text-green-700',
  ordering_physician: 'bg-yellow-100 text-yellow-700',
}

const BLANK: CreateUserPayload = {
  username: '',
  email: '',
  full_name: '',
  role: '',
  password: '',
}

export default function UsersPage() {
  const { user: currentUser } = useAuth()
  const qc = useQueryClient()

  const canRegister = currentUser?.role === 'admin' || currentUser?.role === 'lab_director'
  const assignableRoles = ROLES_BY_ACTOR[currentUser?.role ?? ''] ?? []

  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState<CreateUserPayload>(BLANK)
  const [formError, setFormError] = useState('')

  const { data: users = [], isLoading, error } = useQuery({
    queryKey: ['users'],
    queryFn: usersApi.list,
  })

  const createMutation = useMutation({
    mutationFn: usersApi.create,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['users'] })
      setForm(BLANK)
      setShowForm(false)
      setFormError('')
    },
    onError: (err: any) => {
      setFormError(err?.response?.data?.error ?? 'Failed to create user')
    },
  })

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    setFormError('')
    if (form.password.length < 12) {
      setFormError('Password must be at least 12 characters')
      return
    }
    createMutation.mutate(form)
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Users</h1>
          <p className="text-sm text-gray-500 mt-0.5">{users.length} registered users</p>
        </div>
        {canRegister && (
          <button
            onClick={() => { setShowForm(!showForm); setFormError('') }}
            className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition-colors"
          >
            {showForm ? 'Cancel' : 'Register User'}
          </button>
        )}
      </div>

      {/* Registration form */}
      {showForm && canRegister && (
        <div className="bg-white rounded-xl shadow-sm border p-6">
          <h2 className="text-lg font-semibold text-gray-800 mb-4">Register New User</h2>
          <form onSubmit={handleSubmit} className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Full Name</label>
              <input
                type="text"
                required
                value={form.full_name}
                onChange={(e) => setForm({ ...form, full_name: e.target.value })}
                className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Username</label>
              <input
                type="text"
                required
                value={form.username}
                onChange={(e) => setForm({ ...form, username: e.target.value })}
                className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
              <input
                type="email"
                required
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Role</label>
              <select
                required
                value={form.role}
                onChange={(e) => setForm({ ...form, role: e.target.value })}
                className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
              >
                <option value="">Select role…</option>
                {assignableRoles.map((r) => (
                  <option key={r} value={r}>{ROLE_LABELS[r]}</option>
                ))}
              </select>
            </div>
            <div className="sm:col-span-2">
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Password <span className="text-gray-400 font-normal">(min 12 characters)</span>
              </label>
              <input
                type="password"
                required
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            {formError && (
              <div className="sm:col-span-2">
                <p className="text-sm text-red-600 bg-red-50 px-3 py-2 rounded">{formError}</p>
              </div>
            )}

            <div className="sm:col-span-2 flex justify-end">
              <button
                type="submit"
                disabled={createMutation.isPending}
                className="px-6 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
              >
                {createMutation.isPending ? 'Registering…' : 'Register'}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Users table */}
      <div className="bg-white rounded-xl shadow-sm border overflow-hidden">
        {isLoading && (
          <div className="py-16 text-center text-gray-400 text-sm">Loading users…</div>
        )}
        {error && (
          <div className="py-16 text-center text-red-500 text-sm">Failed to load users</div>
        )}
        {!isLoading && !error && users.length === 0 && (
          <div className="py-16 text-center text-gray-400 text-sm">No users found</div>
        )}
        {!isLoading && users.length > 0 && (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b">
              <tr>
                <th className="px-4 py-3 text-left font-medium text-gray-600">Name</th>
                <th className="px-4 py-3 text-left font-medium text-gray-600">Username</th>
                <th className="px-4 py-3 text-left font-medium text-gray-600">Email</th>
                <th className="px-4 py-3 text-left font-medium text-gray-600">Role</th>
                <th className="px-4 py-3 text-left font-medium text-gray-600">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {users.map((u) => (
                <tr key={u.user_id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3 font-medium text-gray-900">{u.full_name}</td>
                  <td className="px-4 py-3 text-gray-600 font-mono">{u.username}</td>
                  <td className="px-4 py-3 text-gray-600">{u.email}</td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${ROLE_BADGE_COLOURS[u.role] ?? 'bg-gray-100 text-gray-600'}`}>
                      {ROLE_LABELS[u.role] ?? u.role}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${u.is_active ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'}`}>
                      {u.is_active ? 'Active' : 'Inactive'}
                    </span>
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
