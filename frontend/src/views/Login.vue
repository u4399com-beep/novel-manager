<template>
  <div class="login-wrapper">
    <div class="login-card">
      <h1>📚 小说管理系统</h1>
      <p class="subtitle">Novel Manager</p>
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        @submit.prevent="handleLogin"
      >
        <el-form-item label="用户名" prop="username">
          <el-input
            v-model="form.username"
            placeholder="请输入用户名"
            :prefix-icon="User"
            size="large"
          />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="请输入密码"
            :prefix-icon="Lock"
            size="large"
            show-password
          />
        </el-form-item>
        <el-form-item>
          <el-button
            type="primary"
            size="large"
            :loading="loading"
            @click="handleLogin"
            style="width: 100%"
          >
            登 录
          </el-button>
        </el-form-item>
      </el-form>
      <p class="register-hint">
        还没有账号？
        <el-button link type="primary" @click="showRegister = true">立即注册</el-button>
      </p>

      <!-- Register Dialog -->
      <el-dialog v-model="showRegister" title="注册管理员账号" width="420px">
        <el-form
          ref="regFormRef"
          :model="regForm"
          :rules="regRules"
          label-position="top"
        >
          <el-form-item label="用户名" prop="username">
            <el-input v-model="regForm.username" placeholder="至少3个字符" />
          </el-form-item>
          <el-form-item label="邮箱" prop="email">
            <el-input v-model="regForm.email" placeholder="your@email.com" />
          </el-form-item>
          <el-form-item label="密码" prop="password">
            <el-input
              v-model="regForm.password"
              type="password"
              placeholder="至少6个字符"
              show-password
            />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="showRegister = false">取消</el-button>
          <el-button type="primary" :loading="regLoading" @click="handleRegister">
            注册
          </el-button>
        </template>
      </el-dialog>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { User, Lock } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { authApi } from '@/api/auth'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const formRef = ref()
const form = reactive({ username: '', password: '' })
const loading = ref(false)

const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function handleLogin() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  loading.value = true
  try {
    await authStore.login(form.username, form.password)
    ElMessage.success('登录成功')
    const redirect = route.query.redirect as string || '/dashboard'
    // Only allow same-origin redirects (prevent open redirect phishing)
    router.push(redirect.startsWith('/') ? redirect : '/dashboard')
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '登录失败')
  } finally {
    loading.value = false
  }
}

// Register
const showRegister = ref(false)
const regFormRef = ref()
const regLoading = ref(false)
const regForm = reactive({ username: '', email: '', password: '' })
const regRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, message: '至少3个字符', trigger: 'blur' },
  ],
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '请输入有效的邮箱', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '至少6个字符', trigger: 'blur' },
  ],
}

async function handleRegister() {
  const valid = await regFormRef.value?.validate().catch(() => false)
  if (!valid) return

  regLoading.value = true
  try {
    await authApi.register(regForm.username, regForm.email, regForm.password)
    ElMessage.success('注册成功，请登录')
    showRegister.value = false
    form.username = regForm.username
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '注册失败')
  } finally {
    regLoading.value = false
  }
}
</script>

<style scoped>
.login-wrapper {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.login-card {
  width: 400px;
  background: #fff;
  border-radius: 12px;
  padding: 40px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.15);
}

.login-card h1 {
  text-align: center;
  margin: 0 0 4px 0;
  font-size: 24px;
}

.subtitle {
  text-align: center;
  color: #909399;
  font-size: 14px;
  margin: 0 0 32px 0;
}

.register-hint {
  text-align: center;
  color: #909399;
  margin: 0;
}
</style>
