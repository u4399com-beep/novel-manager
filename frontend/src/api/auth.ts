import request from '@/utils/request'

export interface UserInfo {
  id: string
  username: string
  email: string
  role: string
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface LoginResponse {
  access_token: string
  token_type: string
  user: UserInfo
}

export const authApi = {
  login(username: string, password: string): Promise<LoginResponse> {
    return request.post('/auth/login', { username, password }).then((r) => r.data)
  },

  register(username: string, email: string, password: string): Promise<UserInfo> {
    return request.post('/auth/register', { username, email, password }).then((r) => r.data)
  },

  getMe(): Promise<UserInfo> {
    return request.get('/auth/me').then((r) => r.data)
  },
}
