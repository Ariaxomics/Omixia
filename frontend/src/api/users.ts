import client from './client'

export interface UserRecord {
  user_id: string
  username: string
  email: string
  role: string
  full_name: string
  is_active: boolean
  created_at: string
}

export interface CreateUserPayload {
  username: string
  email: string
  full_name: string
  role: string
  password: string
}

export const usersApi = {
  list: () => client.get<{ data: UserRecord[] }>('/users').then((r) => r.data.data),

  create: (payload: CreateUserPayload) =>
    client.post<{ data: UserRecord }>('/users', payload).then((r) => r.data.data),
}
