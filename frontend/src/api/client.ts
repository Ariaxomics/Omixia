import axios from 'axios'

const client = axios.create({
  baseURL: '/api',
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
