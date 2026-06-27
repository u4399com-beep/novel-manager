<template>
  <div>
    <div class="page-header">
      <h2>📊 仪表盘</h2>
      <p>小说管理系统概览</p>
    </div>

    <div class="stats-row">
      <div class="stat-card">
        <div class="stat-icon" style="background: linear-gradient(135deg, #667eea, #764ba2)">
          <el-icon size="24"><Reading /></el-icon>
        </div>
        <div>
          <div class="stat-value">{{ stats.total_novels }}</div>
          <div class="stat-label">小说总数</div>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-icon" style="background: linear-gradient(135deg, #f093fb, #f5576c)">
          <el-icon size="24"><Document /></el-icon>
        </div>
        <div>
          <div class="stat-value">{{ stats.total_chapters }}</div>
          <div class="stat-label">章节总数</div>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-icon" style="background: linear-gradient(135deg, #4facfe, #00f2fe)">
          <el-icon size="24"><Edit /></el-icon>
        </div>
        <div>
          <div class="stat-value">{{ formatNumber(stats.total_words) }}</div>
          <div class="stat-label">总字数</div>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-icon" style="background: linear-gradient(135deg, #43e97b, #38f9d7)">
          <el-icon size="24"><Download /></el-icon>
        </div>
        <div>
          <div class="stat-value">{{ stats.active_tasks }}</div>
          <div class="stat-label">活跃爬取任务</div>
        </div>
      </div>
    </div>

    <!-- Recent Novels -->
    <div class="content-card">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px">
        <h3 style="margin: 0">最近更新</h3>
        <el-button type="primary" @click="$router.push('/novels')">查看全部</el-button>
      </div>
      <el-table :data="recentNovels" stripe v-loading="loading" empty-text="暂无小说数据">
        <el-table-column prop="title" label="小说名称" min-width="200">
          <template #default="{ row }">
            <el-link type="primary" @click="$router.push(`/novels/${row.id}`)">{{ row.title }}</el-link>
          </template>
        </el-table-column>
        <el-table-column prop="author" label="作者" width="150" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="total_chapters" label="章节数" width="100" />
        <el-table-column prop="updated_at" label="更新时间" width="180">
          <template #default="{ row }">
            {{ formatDate(row.updated_at) }}
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { Reading, Document, Edit, Download } from '@element-plus/icons-vue'
import { novelsApi, type NovelRecord } from '@/api/novels'

const loading = ref(false)
const recentNovels = ref<NovelRecord[]>([])

const stats = reactive({
  total_novels: 0,
  total_chapters: 0,
  total_words: 0,
  active_tasks: 0,
})

function statusType(status: string) {
  const map: Record<string, string> = { ongoing: 'success', completed: 'info', hiatus: 'warning' }
  return map[status] || 'info'
}

function statusLabel(status: string) {
  const map: Record<string, string> = { ongoing: '连载中', completed: '已完结', hiatus: '停更' }
  return map[status] || status
}

function formatDate(dateStr: string) {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('zh-CN')
}

function formatNumber(n: number) {
  if (n >= 10000) return (n / 10000).toFixed(1) + '万'
  return n.toLocaleString()
}

async function loadData() {
  loading.value = true
  try {
    const res = await novelsApi.list({ size: 10, sort_by: 'updated_at', sort_dir: 'desc' })
    recentNovels.value = res.items
    stats.total_novels = res.total

    // Calculate total chapters for visible novels
    stats.total_chapters = res.items.reduce((sum, n) => sum + n.total_chapters, 0)
  } catch (e) {
    console.error('Failed to load dashboard data', e)
  } finally {
    loading.value = false
  }
}

onMounted(loadData)
</script>
