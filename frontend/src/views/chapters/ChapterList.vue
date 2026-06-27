<template>
  <div v-loading="loading">
    <div class="page-header">
      <h2>📖 章节管理</h2>
      <p>
        <el-button text @click="$router.push('/novels')">小说管理</el-button>
        <span style="margin: 0 4px">/</span>
        <el-button text @click="$router.push(`/novels/${novelId}`)">{{ novel?.title }}</el-button>
        <span style="margin: 0 4px">/</span>
        <span>章节</span>
      </p>
    </div>

    <div class="content-card">
      <!-- Novel info bar -->
      <div v-if="novel" style="margin-bottom: 16px; padding: 12px; background: #f5f7fa; border-radius: 4px">
        <span style="font-size: 16px; font-weight: bold">{{ novel.title }}</span>
        <span style="color: #909399; margin-left: 12px">{{ novel.author }}</span>
        <el-tag :type="statusType(novel.status)" size="small" style="margin-left: 12px">
          {{ statusLabel(novel.status) }}
        </el-tag>
        <span style="color: #909399; margin-left: 12px">共 {{ pagination.total }} 章</span>
      </div>

      <!-- Toolbar -->
      <div class="toolbar-row">
        <el-button type="primary" @click="$router.push(`/novels/${novelId}/chapters/new`)">添加章节</el-button>
        <el-button @click="showBatchDialog = true">批量添加</el-button>
        <el-popconfirm title="确定删除选中章节?" @confirm="batchDelete">
          <template #reference>
            <el-button :disabled="selectedIds.length === 0" type="danger">批量删除</el-button>
          </template>
        </el-popconfirm>
        <div style="flex: 1" />
        <span v-if="selectedIds.length" style="color: #409eff">已选 {{ selectedIds.length }} 章</span>
      </div>

      <!-- Table -->
      <el-table
        :data="chapters"
        stripe
        @selection-change="handleSelectionChange"
        row-key="id"
      >
        <el-table-column type="selection" width="50" />
        <el-table-column prop="sort_order" label="序号" width="70" />
        <el-table-column prop="title" label="章节标题" min-width="250">
          <template #default="{ row }">
            <el-link type="primary" @click="$router.push(`/novels/${novelId}/chapters/${row.id}`)">
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
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="$router.push(`/novels/${novelId}/chapters/${row.id}`)">编辑</el-button>
            <el-popconfirm title="确定删除该章节?" @confirm="handleDelete(row.id)">
              <template #reference>
                <el-button link type="danger">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>

      <!-- Pagination -->
      <div style="margin-top: 16px; display: flex; justify-content: flex-end">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.size"
          :total="pagination.total"
          :page-sizes="[20, 50, 100]"
          layout="total, sizes, prev, pager, next"
          @change="loadChapters"
        />
      </div>
    </div>

    <!-- Batch Create Dialog -->
    <el-dialog v-model="showBatchDialog" title="批量添加章节" width="600px">
      <p style="color: #909399; margin-bottom: 12px">每行一个章节标题，章节将按顺序自动编号。</p>
      <el-input
        v-model="batchTitles"
        type="textarea"
        :rows="10"
        placeholder="第一章 楔子&#10;第二章 开始&#10;第三章 成长"
      />
      <template #footer>
        <el-button @click="showBatchDialog = false">取消</el-button>
        <el-button type="primary" :loading="batchSubmitting" @click="handleBatchCreate">
          批量创建
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { novelsApi, type NovelRecord } from '@/api/novels'
import { chaptersApi, type ChapterRecord } from '@/api/chapters'

const route = useRoute()
const novelId = route.params.novelId as string
const loading = ref(false)
const novel = ref<NovelRecord | null>(null)
const chapters = ref<ChapterRecord[]>([])
const selectedIds = ref<string[]>([])

const pagination = reactive({ page: 1, size: 50, total: 0 })

// Batch create
const showBatchDialog = ref(false)
const batchTitles = ref('')
const batchSubmitting = ref(false)

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

function handleSelectionChange(selection: ChapterRecord[]) {
  selectedIds.value = selection.map((c) => c.id)
}

async function loadChapters() {
  loading.value = true
  try {
    const res = await chaptersApi.list(novelId, { page: pagination.page, size: pagination.size })
    chapters.value = res.items
    pagination.total = res.total
  } catch (e) {
    console.error('Failed to load chapters', e)
  } finally {
    loading.value = false
  }
}

async function handleDelete(chapterId: string) {
  try {
    await chaptersApi.delete(novelId, chapterId)
    ElMessage.success('章节已删除')
    await loadChapters()
  } catch (e) { /* ignore */ }
}

async function batchDelete() {
  try {
    await chaptersApi.batchDelete(novelId, selectedIds.value)
    ElMessage.success(`已删除 ${selectedIds.value.length} 个章节`)
    selectedIds.value = []
    await loadChapters()
  } catch (e) { /* ignore */ }
}

async function handleBatchCreate() {
  const titles = batchTitles.value
    .split('\n')
    .map((t) => t.trim())
    .filter((t) => t.length > 0)

  if (titles.length === 0) {
    ElMessage.warning('请输入至少一个章节标题')
    return
  }

  batchSubmitting.value = true
  try {
    const chapterList = titles.map((title) => ({ title }))
    await chaptersApi.batchCreate(novelId, chapterList)
    ElMessage.success(`成功创建 ${titles.length} 个章节`)
    showBatchDialog.value = false
    batchTitles.value = ''
    await loadChapters()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '批量创建失败')
  } finally {
    batchSubmitting.value = false
  }
}

onMounted(async () => {
  try {
    novel.value = await novelsApi.get(novelId)
  } catch (e) { /* ignore */ }
  loadChapters()
})
</script>
