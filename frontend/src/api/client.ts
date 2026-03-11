import axios from 'axios'

// In local dev, VITE_API_BASE_URL is unset → falls back to nginx proxy at /api
// In production (Cloudflare Pages), set VITE_API_BASE_URL=https://api.yourdomain.com/api
const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api'

const client = axios.create({
  baseURL: BASE_URL,
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
})

client.interceptors.response.use(
  (r) => r,
  (err) => {
    const url: string = err.config?.url ?? ''
    const is401 = err.response?.status === 401
    // Don't redirect on the initial session check — AuthContext handles that
    if (is401 && !url.includes('/auth/me')) {
      window.location.href = '/login'
    }
    return Promise.reject(err)
  },
)

export default client
