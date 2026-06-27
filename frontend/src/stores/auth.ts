import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi } from '@/api/auth'
import type { UserInfo } from '@/api/auth'

export const useAuthStore = defineStore('auth', () => {
  // State
  const token = ref<string>(localStorage.getItem('token') || '')
  const user = ref<UserInfo | null>(null)

  // Getters
  const isAuthenticated = computed(() => !!token.value)

  // Actions
  async function login(username: string, password: string): Promise<void> {
    const res = await authApi.login(username, password)
    token.value = res.access_token
    user.value = res.user
    localStorage.setItem('token', res.access_token)
  }

  async function fetchMe(): Promise<void> {
    if (!token.value) return
    try {
      user.value = await authApi.getMe()
    } catch {
      logout()
    }
  }

  function logout(): void {
    token.value = ''
    user.value = null
    localStorage.removeItem('token')
  }

  return { token, user, isAuthenticated, login, fetchMe, logout }
})
