import client from './client'

export interface User {
  user_id: string
  username: string
  role: string
  full_name: string
  email: string
}

export const authApi = {
  login: async (username: string, password: string): Promise<User> => {
    const res = await client.post('/auth/login', { username, password })
    return res.data.data
  },
  logout: async () => {
    await client.post('/auth/logout')
  },
  me: async (): Promise<User> => {
    const res = await client.get('/auth/me')
    return res.data.data
  },
}
