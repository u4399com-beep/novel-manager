<template>
  <el-container class="app-layout">
    <el-aside :width="isCollapse ? '64px' : '220px'">
      <div class="sidebar-logo">
        <span v-if="!isCollapse">📚 Novel Manager</span>
        <span v-else>📚</span>
      </div>
      <el-menu
        :default-active="activeMenu"
        router
        :collapse="isCollapse"
        background-color="#304156"
        text-color="#bfcbd9"
        active-text-color="#409EFF"
      >
        <el-menu-item index="/dashboard">
          <el-icon><Odometer /></el-icon>
          <span>仪表盘</span>
        </el-menu-item>
        <el-menu-item index="/novels">
          <el-icon><Reading /></el-icon>
          <span>小说管理</span>
        </el-menu-item>
        <el-menu-item index="/categories">
          <el-icon><Collection /></el-icon>
          <span>分类管理</span>
        </el-menu-item>
        <el-menu-item index="/crawler">
          <el-icon><Download /></el-icon>
          <span>爬取任务</span>
        </el-menu-item>
        <el-menu-item index="/rules">
          <el-icon><Setting /></el-icon>
          <span>采集规则</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header>
        <div style="display: flex; align-items: center; gap: 12px">
          <el-button
            :icon="isCollapse ? Expand : Fold"
            text
            @click="isCollapse = !isCollapse"
          />
          <el-breadcrumb separator="/">
            <el-breadcrumb-item :to="{ path: '/dashboard' }">首页</el-breadcrumb-item>
            <el-breadcrumb-item v-if="pageTitle">{{ pageTitle }}</el-breadcrumb-item>
          </el-breadcrumb>
        </div>
        <div style="display: flex; align-items: center; gap: 12px">
          <el-tag type="info" size="small">{{ authStore.user?.username }}</el-tag>
          <el-button text @click="handleLogout">退出登录</el-button>
        </div>
      </el-header>
      <el-main>
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import {
  Odometer,
  Reading,
  Collection,
  Download,
  Expand,
  Fold,
  Setting,
} from '@element-plus/icons-vue'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const isCollapse = ref(false)

const activeMenu = computed(() => {
  const path = route.path
  if (path.startsWith('/novels')) return '/novels'
  if (path.startsWith('/categories')) return '/categories'
  if (path.startsWith('/crawler')) return '/crawler'
  return path
})

const pageTitle = computed(() => {
  const map: Record<string, string> = {
    '/dashboard': '仪表盘',
    '/novels': '小说管理',
    '/categories': '分类管理',
    '/crawler': '爬取任务',
  }
  return map[route.path] || ''
})

function handleLogout() {
  authStore.logout()
  router.push('/login')
}
</script>
