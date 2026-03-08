import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'

const navItems = [
  { to: '/dashboard', label: 'Dashboard' },
  { to: '/samples', label: 'Samples' },
  { to: '/knowledge', label: 'Knowledge DB' },
  { to: '/cohort', label: 'Cohort' },
  { to: '/lab-dashboard', label: 'Lab Dashboard' },
  { to: '/gap-analysis', label: 'Gap Analysis' },
]

export default function Layout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <nav className="bg-blue-700 text-white shadow-sm">
        <div className="max-w-7xl mx-auto px-4 flex items-center h-14 gap-6">
          <span className="font-bold text-lg tracking-tight mr-2">Omixia</span>
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `text-sm font-medium px-2 py-1 rounded transition-colors ${
                  isActive ? 'bg-blue-900' : 'hover:bg-blue-600'
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
          <div className="ml-auto flex items-center gap-3 text-sm">
            <span className="opacity-80">{user?.full_name || user?.username}</span>
            <span className="px-2 py-0.5 rounded bg-blue-500 text-xs font-medium capitalize">
              {user?.role?.replace('_', ' ')}
            </span>
            <button
              onClick={handleLogout}
              className="px-3 py-1 rounded bg-blue-800 hover:bg-blue-900 transition-colors"
            >
              Logout
            </button>
          </div>
        </div>
      </nav>
      <main className="flex-1 max-w-7xl mx-auto w-full px-4 py-6">
        <Outlet />
      </main>
    </div>
  )
}
