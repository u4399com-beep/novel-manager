<template>
  <div>
    <div class="page-header">
      <h2>{{ isEdit ? '编辑小说' : '添加小说' }}</h2>
      <p>{{ isEdit ? '修改小说信息' : '添加一本新小说' }}</p>
    </div>

    <div class="content-card" style="max-width: 720px">
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="100px"
        v-loading="loading"
      >
        <el-form-item label="小说名称" prop="title">
          <el-input v-model="form.title" placeholder="请输入小说名称" />
        </el-form-item>
        <el-form-item label="作者" prop="author">
          <el-input v-model="form.author" placeholder="请输入作者名" />
        </el-form-item>
        <el-form-item label="状态" prop="status">
          <el-radio-group v-model="form.status">
            <el-radio-button value="ongoing">连载中</el-radio-button>
            <el-radio-button value="completed">已完结</el-radio-button>
            <el-radio-button value="hiatus">停更</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="分类">
          <el-select v-model="form.category_ids" multiple placeholder="选择分类" style="width: 100%">
            <el-option
              v-for="cat in categories"
              :key="cat.id"
              :label="cat.name"
              :value="cat.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="简介" prop="description">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="4"
            placeholder="请输入小说简介"
          />
        </el-form-item>
        <el-form-item label="外部源名称">
          <el-input v-model="form.source_name" placeholder="如: qidian, zongheng" />
        </el-form-item>
        <el-form-item label="外部源URL">
          <el-input v-model="form.source_url" placeholder="外部小说源地址（用于爬取）" />
        </el-form-item>
        <el-form-item label="封面图片">
          <el-upload
            v-if="!isEdit"
            action=""
            :auto-upload="false"
            :show-file-list="false"
            :on-change="handleCoverChange"
            accept="image/*"
          >
            <el-button type="primary">选择封面图片</el-button>
          </el-upload>
          <div v-if="coverPreview" style="margin-top: 8px">
            <el-image :src="coverPreview" style="width: 120px; height: 160px; border-radius: 4px" fit="cover" />
          </div>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="submitting" @click="handleSubmit">
            {{ isEdit ? '保存修改' : '创建小说' }}
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
import { novelsApi } from '@/api/novels'
import { categoriesApi, type CategoryRecord } from '@/api/categories'

const route = useRoute()
const router = useRouter()
const formRef = ref()
const loading = ref(false)
const submitting = ref(false)
const categories = ref<CategoryRecord[]>([])
const coverPreview = ref('')
const coverFile = ref<File | null>(null)

const novelId = computed(() => route.params.id as string)
const isEdit = computed(() => !!novelId.value)

const form = reactive({
  title: '',
  author: '',
  status: 'ongoing',
  description: '',
  source_name: '',
  source_url: '',
  category_ids: [] as number[],
})

const rules = {
  title: [{ required: true, message: '请输入小说名称', trigger: 'blur' }],
  author: [{ required: true, message: '请输入作者名', trigger: 'blur' }],
}

function handleCoverChange(file: any) {
  coverFile.value = file.raw
  coverPreview.value = URL.createObjectURL(file.raw)
}

async function handleSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  submitting.value = true
  try {
    if (isEdit.value) {
      await novelsApi.update(novelId.value, { ...form })
      ElMessage.success('小说信息已更新')
    } else {
      const novel = await novelsApi.create({ ...form })
      // Upload cover if selected
      if (coverFile.value) {
        await novelsApi.uploadCover(novel.id, coverFile.value)
      }
      ElMessage.success('小说创建成功')
    }
    router.push('/novels')
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  try {
    categories.value = await categoriesApi.list()
  } catch (e) { /* ignore */ }

  if (isEdit.value) {
    loading.value = true
    try {
      const novel = await novelsApi.get(novelId.value)
      Object.assign(form, {
        title: novel.title,
        author: novel.author,
        status: novel.status,
        description: novel.description || '',
        source_name: novel.source_name || '',
        source_url: novel.source_url || '',
        category_ids: novel.categories.map((c: any) => c.id),
      })
      if (novel.cover_image_url) {
        coverPreview.value = novel.cover_image_url
      }
    } catch (e) {
      ElMessage.error('加载小说信息失败')
    } finally {
      loading.value = false
    }
  }
})
</script>
