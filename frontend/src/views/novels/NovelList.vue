<template>
  <div>
    <div class="page-header">
      <h2>📚 小说管理</h2>
      <p>管理所有小说资源</p>
    </div>

    <div class="content-card">
      <!-- Toolbar -->
      <div class="toolbar-row">
        <el-input
          v-model="filters.search"
          placeholder="搜索小说名/作者..."
          :prefix-icon="Search"
          clearable
          @keyup.enter="loadNovels"
          @clear="loadNovels"
        />
        <el-select v-model="filters.category_id" placeholder="分类筛选" clearable @change="loadNovels" style="width: 160px">
          <el-option
            v-for="cat in categories"
            :key="cat.id"
            :label="cat.name"
            :value="cat.id"
          />
        </el-select>
        <el-select v-model="filters.status" placeholder="状态筛选" clearable @change="loadNovels" style="width: 130px">
          <el-option label="连载中" value="ongoing" />
          <el-option label="已完结" value="completed" />
          <el-option label="停更" value="hiatus" />
        </el-select>
        <el-button type="primary" :icon="Search" @click="loadNovels">搜索</el-button>
        <div style="flex: 1" />
        <el-button type="primary" :icon="Plus" @click="$router.push('/novels/create')">添加小说</el-button>
      </div>

      <!-- Table -->
      <el-table :data="novels" stripe v-loading="loading" @sort-change="handleSortChange">
        <el-table-column prop="title" label="小说名称" min-width="200" sortable="custom">
          <template #default="{ row }">
            <div style="display: flex; align-items: center; gap: 12px">
              <el-avatar v-if="row.cover_image_url" :src="row.cover_image_url" shape="square" size="small" />
              <el-link type="primary" @click="$router.push(`/novels/${row.id}`)">{{ row.title }}</el-link>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="author" label="作者" width="130" sortable="custom" />
        <el-table-column prop="status" label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="total_chapters" label="章节数" width="90" sortable="custom" />
        <el-table-column label="分类" width="180">
          <template #default="{ row }">
            <el-tag v-for="cat in row.categories" :key="cat.id" size="small" style="margin-right: 4px">
              {{ cat.name }}
            </el-tag>
            <span v-if="!row.categories?.length" style="color: #c0c4cc">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="updated_at" label="更新时间" width="170" sortable="custom">
          <template #default="{ row }">
            {{ formatDate(row.updated_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="$router.push(`/novels/${row.id}`)">详情</el-button>
            <el-button link type="warning" @click="$router.push(`/novels/${row.id}/edit`)">编辑</el-button>
            <el-popconfirm title="确定删除该小说及其所有章节?" @confirm="handleDelete(row.id)">
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
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          @change="loadNovels"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { Search, Plus } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { novelsApi, type NovelRecord } from '@/api/novels'
import { categoriesApi, type CategoryRecord } from '@/api/categories'

const loading = ref(false)
const novels = ref<NovelRecord[]>([])
const categories = ref<CategoryRecord[]>([])

const filters = reactive({
  search: '',
  category_id: undefined as number | undefined,
  status: '' as string | undefined,
  sort_by: 'updated_at',
  sort_dir: 'desc' as 'asc' | 'desc',
})

const pagination = reactive({ page: 1, size: 20, total: 0 })

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

function handleSortChange({ prop, order }: any) {
  if (prop && order) {
    filters.sort_by = prop
    filters.sort_dir = order === 'ascending' ? 'asc' : 'desc'
  } else {
    filters.sort_by = 'updated_at'
    filters.sort_dir = 'desc'
  }
  loadNovels()
}

async function loadNovels() {
  loading.value = true
  try {
    const res = await novelsApi.list({
      page: pagination.page,
      size: pagination.size,
      ...filters,
    })
    novels.value = res.items
    pagination.total = res.total
  } catch (e: any) {
    console.error('Failed to load novels', e)
    ElMessage.error('加载小说列表失败')
  } finally {
    loading.value = false
  }
}

async function handleDelete(id: string) {
  try {
    await novelsApi.delete(id)
    await loadNovels()
  } catch (e: any) {
    console.error('Failed to delete novel', e)
    ElMessage.error('删除失败')
  }
}

onMounted(async () => {
  try {
    categories.value = await categoriesApi.list()
  } catch (e: any) {
    console.error('Failed to load categories', e)
  }
  loadNovels()
})
</script>
