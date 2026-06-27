<template>
  <div>
    <div class="page-header">
      <h2>🏷️ 分类管理</h2>
      <p>管理小说分类标签</p>
    </div>

    <div class="content-card">
      <div style="margin-bottom: 16px">
        <el-button type="primary" :icon="Plus" @click="showCreateDialog">添加分类</el-button>
      </div>

      <el-table :data="categories" stripe v-loading="loading" empty-text="暂无分类">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="name" label="名称" width="150" />
        <el-table-column prop="slug" label="标识" width="150" />
        <el-table-column prop="description" label="描述" min-width="200">
          <template #default="{ row }">{{ row.description || '-' }}</template>
        </el-table-column>
        <el-table-column prop="sort_order" label="排序" width="80" />
        <el-table-column label="操作" width="160">
          <template #default="{ row }">
            <el-button link type="warning" @click="handleEdit(row)">编辑</el-button>
            <el-popconfirm title="确定删除该分类?" @confirm="handleDelete(row.id)">
              <template #reference>
                <el-button link type="danger">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- Create/Edit Dialog -->
    <el-dialog
      v-model="dialogVisible"
      :title="isEditing ? '编辑分类' : '添加分类'"
      width="460px"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" placeholder="如: 玄幻" />
        </el-form-item>
        <el-form-item label="标识" prop="slug">
          <el-input v-model="form.slug" placeholder="如: xuanhuan" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" placeholder="分类描述（可选）" />
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="form.sort_order" :min="0" :max="999" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { categoriesApi, type CategoryRecord } from '@/api/categories'

const loading = ref(false)
const categories = ref<CategoryRecord[]>([])
const dialogVisible = ref(false)
const isEditing = ref(false)
const submitting = ref(false)
const editingId = ref<number | null>(null)
const formRef = ref()

const form = reactive({
  name: '',
  slug: '',
  description: '',
  sort_order: 0,
})

const rules = {
  name: [{ required: true, message: '请输入分类名称', trigger: 'blur' }],
  slug: [{ required: true, message: '请输入分类标识', trigger: 'blur' }],
}

function showCreateDialog() {
  isEditing.value = false
  editingId.value = null
  form.name = ''
  form.slug = ''
  form.description = ''
  form.sort_order = 0
  dialogVisible.value = true
}

function handleEdit(row: CategoryRecord) {
  isEditing.value = true
  editingId.value = row.id
  form.name = row.name
  form.slug = row.slug
  form.description = row.description || ''
  form.sort_order = row.sort_order
  dialogVisible.value = true
}

async function handleSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  submitting.value = true
  try {
    if (isEditing.value && editingId.value) {
      await categoriesApi.update(editingId.value, { ...form })
      ElMessage.success('分类已更新')
    } else {
      await categoriesApi.create({ ...form })
      ElMessage.success('分类已创建')
    }
    dialogVisible.value = false
    await loadCategories()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
  } finally {
    submitting.value = false
  }
}

async function handleDelete(id: number) {
  try {
    await categoriesApi.delete(id)
    ElMessage.success('分类已删除')
    await loadCategories()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

async function loadCategories() {
  loading.value = true
  try {
    categories.value = await categoriesApi.list()
  } catch (e) {
    console.error('Failed to load categories', e)
  } finally {
    loading.value = false
  }
}

onMounted(loadCategories)
</script>
