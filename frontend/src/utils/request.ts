import axios from 'axios'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'

const request = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
})

// Request interceptor - attach JWT token
request.interceptors.request.use(
  (config) => {
    const authStore = useAuthStore()
    if (authStore.token) {
      config.headers.Authorization = `Bearer ${authStore.token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// Response interceptor - handle errors
request.interceptors.response.use(
  (response) => response,
  (error) => {
    const message = error.response?.data?.detail || error.message || 'Request failed'

    if (error.response?.status === 401) {
      const authStore = useAuthStore()
      authStore.logout()
      window.location.href = '/login'
    } else if (error.response?.status === 403) {
      ElMessage.error('Permission denied')
    } else if (error.response?.status === 404) {
      ElMessage.error('Resource not found')
    } else if (error.response?.status === 500) {
      ElMessage.error('Server error: ' + message)
    }

    return Promise.reject(error)
  }
)

export default request
