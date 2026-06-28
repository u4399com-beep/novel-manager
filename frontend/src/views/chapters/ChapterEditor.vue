<template>
  <div v-loading="loading">
    <div class="page-header">
      <h2>{{ isNew ? '新建章节' : '编辑章节' }}</h2>
      <p>
        <el-button text @click="$router.push('/novels')">小说管理</el-button>
        <span style="margin: 0 4px">/</span>
        <el-button text @click="$router.push(`/novels/${novelId}/chapters`)">章节管理</el-button>
        <span style="margin: 0 4px">/</span>
        <span>{{ isNew ? '新建' : chapter?.title }}</span>
      </p>
    </div>

    <div class="content-card" style="max-width: 900px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
        <el-form-item label="章节标题" prop="title">
          <el-input v-model="form.title" placeholder="请输入章节标题" />
        </el-form-item>

        <el-form-item label="排序序号">
          <el-input-number v-model="form.sort_order" :min="1" />
        </el-form-item>

        <el-form-item label="发布状态">
          <el-switch v-model="form.is_published" active-text="已发布" inactive-text="草稿" />
        </el-form-item>

        <el-form-item label="章节内容">
          <el-input
            v-model="form.content"
            type="textarea"
            :rows="20"
            placeholder="请输入章节正文内容..."
          />
          <div style="margin-top: 4px; color: #909399; font-size: 12px">
            字数: {{ wordCount }}
          </div>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" :loading="submitting" @click="handleSubmit">
            {{ isNew ? '创建章节' : '保存修改' }}
          </el-button>
          <el-button @click="$router.back()">取消</el-button>
        </el-form-item>
      </el-form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { chaptersApi } from '@/api/chapters'

const route = useRoute()
const router = useRouter()
const novelId = route.params.novelId as string
const chapterId = route.params.chapterId as string
const isNew = computed(() => chapterId === 'new')
const formRef = ref()
const loading = ref(false)
const submitting = ref(false)
const chapter = ref<import('@/api/chapters').ChapterDetail | null>(null)

const form = reactive({
  title: '',
  content: '',
  sort_order: undefined as number | undefined,
  is_published: true,
})

const rules = {
  title: [{ required: true, message: '请输入章节标题', trigger: 'blur' }],
}

const wordCount = computed(() => {
  if (!form.content) return 0
  const chinese = (form.content.match(/[一-鿿]/g) || []).length
  const english = (form.content.match(/[a-zA-Z]+/g) || []).length
  return chinese + english
})

async function handleSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  submitting.value = true
  try {
    if (isNew.value) {
      const ch = await chaptersApi.create(novelId, { ...form })
      ElMessage.success('章节已创建')
      router.push(`/novels/${novelId}/chapters/${ch.id}`)
    } else {
      await chaptersApi.update(novelId, chapterId, { ...form })
      ElMessage.success('章节已更新')
    }
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  if (!isNew.value) {
    loading.value = true
    try {
      const ch = await chaptersApi.get(novelId, chapterId)
      chapter.value = ch
      form.title = ch.title
      form.content = ch.content || ''
      form.sort_order = ch.sort_order
      form.is_published = ch.is_published
    } catch (e) {
      ElMessage.error('加载章节失败')
      router.back()
    } finally {
      loading.value = false
    }
  }
})
</script>
