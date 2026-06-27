<template>
  <div v-loading="loading">
    <div class="page-header">
      <h2>{{ novel?.title || '小说详情' }}</h2>
      <p>
        <el-button text @click="$router.push('/novels')">小说管理</el-button>
        <span style="margin: 0 4px">/</span>
        <span>详情</span>
      </p>
    </div>

    <el-row :gutter="20" v-if="novel">
      <!-- Basic Info -->
      <el-col :span="8">
        <div class="content-card">
          <div style="text-align: center; margin-bottom: 16px">
            <el-image
              v-if="novel.cover_image_url"
              :src="novel.cover_image_url"
              style="width: 160px; height: 210px; border-radius: 8px"
              fit="cover"
            />
            <div v-else style="width: 160px; height: 210px; margin: 0 auto; background: #f5f7fa; border-radius: 8px; display: flex; align-items: center; justify-content: center; color: #c0c4cc; font-size: 48px">
              📖
            </div>
          </div>
          <h3 style="text-align: center; margin: 0 0 4px 0">{{ novel.title }}</h3>
          <p style="text-align: center; color: #909399; margin: 0 0 16px 0">{{ novel.author }}</p>

          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="状态">
              <el-tag :type="statusType(novel.status)" size="small">{{ statusLabel(novel.status) }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="章节数">{{ novel.total_chapters }}</el-descriptions-item>
            <el-descriptions-item label="分类">
              <el-tag v-for="cat in novel.categories" :key="cat.id" size="small" style="margin: 2px">
                {{ cat.name }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="外部源">{{ novel.source_name || '-' }}</el-descriptions-item>
            <el-descriptions-item label="创建时间">{{ formatDate(novel.created_at) }}</el-descriptions-item>
            <el-descriptions-item label="更新时间">{{ formatDate(novel.updated_at) }}</el-descriptions-item>
          </el-descriptions>

          <div style="margin-top: 16px; display: flex; gap: 8px">
            <el-button type="primary" @click="$router.push(`/novels/${novel.id}/edit`)">编辑</el-button>
            <el-button type="success" @click="$router.push(`/novels/${novel.id}/chapters`)">管理章节</el-button>
          </div>

          <div style="margin-top: 16px" v-if="novel.description">
            <h4>简介</h4>
            <p style="color: #606266; line-height: 1.8">{{ novel.description }}</p>
          </div>
        </div>
      </el-col>

      <!-- Statistics & Chapters -->
      <el-col :span="16">
        <!-- Stats -->
        <div class="content-card" style="margin-bottom: 16px">
          <h3 style="margin: 0 0 16px 0">📊 数据统计</h3>
          <el-row :gutter="16">
            <el-col :span="8">
              <div class="stat-card" style="box-shadow: none; background: #f5f7fa">
                <div>
                  <div class="stat-value">{{ stats.total_chapters }}</div>
                  <div class="stat-label">总章节</div>
                </div>
              </div>
            </el-col>
            <el-col :span="8">
              <div class="stat-card" style="box-shadow: none; background: #f5f7fa">
                <div>
                  <div class="stat-value">{{ stats.published_chapters }}</div>
                  <div class="stat-label">已发布</div>
                </div>
              </div>
            </el-col>
            <el-col :span="8">
              <div class="stat-card" style="box-shadow: none; background: #f5f7fa">
                <div>
                  <div class="stat-value">{{ formatNumber(stats.total_words) }}</div>
                  <div class="stat-label">总字数</div>
                </div>
              </div>
            </el-col>
          </el-row>
        </div>

        <!-- Chapter Quick List -->
        <div class="content-card">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px">
            <h3 style="margin: 0">📖 最近章节</h3>
            <el-button type="primary" size="small" @click="$router.push(`/novels/${novel.id}/chapters`)">
              查看全部章节
            </el-button>
          </div>
          <el-table :data="recentChapters" stripe empty-text="暂无章节">
            <el-table-column prop="sort_order" label="#" width="60" />
            <el-table-column prop="title" label="章节标题" min-width="200">
              <template #default="{ row }">
                <el-link type="primary" @click="$router.push(`/novels/${novel.id}/chapters/${row.id}`)">
                  {{ row.title }}
                </el-link>
              </template>
            </el-table-column>
            <el-table-column prop="word_count" label="字数" width="100" />
            <el-table-column prop="is_published" label="状态" width="100">
              <template #default="{ row }">
                <el-tag :type="row.is_published ? 'success' : 'info'" size="small">
                  {{ row.is_published ? '已发布' : '草稿' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="updated_at" label="更新时间" width="170">
              <template #default="{ row }">{{ formatDate(row.updated_at) }}</template>
            </el-table-column>
          </el-table>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { novelsApi, type NovelRecord } from '@/api/novels'
import { chaptersApi, type ChapterRecord } from '@/api/chapters'

const route = useRoute()
const loading = ref(false)
const novel = ref<NovelRecord | null>(null)
const recentChapters = ref<ChapterRecord[]>([])

const stats = reactive({
  total_chapters: 0,
  published_chapters: 0,
  total_words: 0,
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

onMounted(async () => {
  const novelId = route.params.id as string
  loading.value = true
  try {
    novel.value = await novelsApi.get(novelId)
    const s = await novelsApi.statistics(novelId)
    Object.assign(stats, s)

    const chRes = await chaptersApi.list(novelId, { size: 10 })
    recentChapters.value = chRes.items
  } catch (e) {
    console.error('Failed to load novel detail', e)
  } finally {
    loading.value = false
  }
})
</script>
