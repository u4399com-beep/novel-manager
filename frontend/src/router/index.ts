import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
    meta: { requiresAuth: false },
  },
  {
    path: '/',
    component: () => import('@/components/layout/AppLayout.vue'),
    meta: { requiresAuth: true },
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/views/Dashboard.vue'),
      },
      {
        path: 'novels',
        name: 'NovelList',
        component: () => import('@/views/novels/NovelList.vue'),
      },
      {
        path: 'novels/create',
        name: 'NovelCreate',
        component: () => import('@/views/novels/NovelForm.vue'),
      },
      {
        path: 'novels/:id',
        name: 'NovelDetail',
        component: () => import('@/views/novels/NovelDetail.vue'),
      },
      {
        path: 'novels/:id/edit',
        name: 'NovelEdit',
        component: () => import('@/views/novels/NovelForm.vue'),
      },
      {
        path: 'novels/:novelId/chapters',
        name: 'ChapterList',
        component: () => import('@/views/chapters/ChapterList.vue'),
      },
      {
        path: 'novels/:novelId/chapters/:chapterId',
        name: 'ChapterEditor',
        component: () => import('@/views/chapters/ChapterEditor.vue'),
      },
      {
        path: 'categories',
        name: 'CategoryList',
        component: () => import('@/views/categories/CategoryList.vue'),
      },
      {
        path: 'crawler',
        name: 'CrawlerTasks',
        component: () => import('@/views/crawler/CrawlerTasks.vue'),
      },
      {
        path: 'rules',
        name: 'RuleEditor',
        component: () => import('@/views/rules/RuleEditor.vue'),
      },
      {
        path: 'sites',
        name: 'SiteList',
        component: () => import('@/views/sites/SiteList.vue'),
      },
      {
        path: 'link-rings',
        name: 'LinkRingList',
        component: () => import('@/views/sites/LinkRingList.vue'),
      },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// Auth guard
router.beforeEach((to, _from, next) => {
  const authStore = useAuthStore()

  if (to.meta.requiresAuth === false) {
    // If logged in and going to login page, redirect to dashboard
    if (authStore.token && to.name === 'Login') {
      next('/dashboard')
    } else {
      next()
    }
    return
  }

  if (!authStore.token) {
    next({ name: 'Login', query: { redirect: to.fullPath } })
  } else {
    next()
  }
})

export default router
