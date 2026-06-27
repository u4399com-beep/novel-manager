<template>
  <div class="rule-editor">
    <div class="page-header">
      <h2>🕷️ 采集规则编辑器</h2>
      <p>可视化编辑和测试网站采集规则</p>
    </div>

    <el-row :gutter="16">
      <!-- Left: Rule List -->
      <el-col :span="5">
        <div class="content-card" style="min-height: 500px">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px">
            <strong>规则列表</strong>
            <el-button size="small" type="primary" @click="createNew">+ 新建</el-button>
          </div>
          <el-menu
            :default-active="activeRule"
            @select="selectRule"
            style="border-right: none"
          >
            <el-menu-item
              v-for="rule in ruleList"
              :key="rule.source_name"
              :index="rule.source_name"
            >
              <span>{{ rule.source_name }}</span>
              <span style="color: #909399; font-size: 12px; margin-left: 8px">{{ rule.description }}</span>
            </el-menu-item>
          </el-menu>
          <el-empty v-if="ruleList.length === 0" description="暂无规则" :image-size="40" />
        </div>
      </el-col>

      <!-- Right: Editor + Test -->
      <el-col :span="19">
        <!-- Toolbar -->
        <div class="content-card" style="margin-bottom: 12px; padding: 8px 16px; display: flex; gap: 8px; align-items: center">
          <span style="font-weight: bold; margin-right: 8px">{{ activeRule || '未选择规则' }}</span>
          <el-button size="small" type="primary" @click="saveRule" :loading="saving">💾 保存</el-button>
          <el-button size="small" @click="formatJson">格式化</el-button>
          <el-popconfirm title="确定删除此规则?" @confirm="deleteCurrentRule">
            <template #reference>
              <el-button size="small" type="danger">删除</el-button>
            </template>
          </el-popconfirm>
          <el-tag v-if="saveMsg" :type="saveMsgType" size="small">{{ saveMsg }}</el-tag>
        </div>

        <el-row :gutter="12">
          <!-- JSON Editor -->
          <el-col :span="14">
            <div class="content-card" style="min-height: 500px">
              <strong style="display: block; margin-bottom: 8px">规则 JSON</strong>
              <el-input
                v-model="jsonText"
                type="textarea"
                :rows="26"
                placeholder="选择或新建一个规则..."
                style="font-family: 'SF Mono', 'Menlo', monospace; font-size: 12px; line-height: 1.5"
              />
            </div>
          </el-col>

          <!-- Test Panel -->
          <el-col :span="10">
            <div class="content-card" style="min-height: 500px">
              <strong style="display: block; margin-bottom: 12px">🧪 在线测试</strong>

              <!-- Section selector -->
              <el-select v-model="testSection" placeholder="选择采集类型" style="width: 100%; margin-bottom: 8px">
                <el-option label="🔍 搜索 (search)" value="search" />
                <el-option label="📖 小说信息 (novel_info)" value="novel_info" />
                <el-option label="📋 章节目录 (catalog)" value="catalog" />
                <el-option label="📄 章节内容 (chapter)" value="chapter" />
              </el-select>

              <!-- Dynamic params -->
              <el-input
                v-if="testSection === 'search'"
                v-model="testKeyword"
                placeholder="搜索关键词"
                style="margin-bottom: 8px"
              />
              <el-input
                v-if="testSection === 'novel_info' || testSection === 'chapter'"
                v-model="testUrl"
                placeholder="页面URL（如 /book/4262/）"
                style="margin-bottom: 8px"
              />
              <el-input
                v-if="testSection === 'catalog'"
                v-model="testBookId"
                placeholder="书籍ID（如 11928）"
                style="margin-bottom: 8px"
              />

              <el-button
                type="primary"
                :loading="testing"
                @click="runTest"
                style="width: 100%; margin-bottom: 12px"
              >
                ▶ 执行测试
              </el-button>

              <!-- Results -->
              <div v-if="testError" style="color: #f56c6c; margin-bottom: 8px">
                ❌ {{ testError }}
              </div>

              <div v-if="testResult">
                <div style="margin-bottom: 8px; color: #67c23a">
                  ✅ 成功 — URL: <a :href="testResult.url" target="_blank" style="font-size: 12px">{{ testResult.url }}</a>
                  <span v-if="testResult.total"> | 共 {{ testResult.total }} 条，显示 {{ testResult.displayed }} 条</span>
                </div>

                <div style="max-height: 350px; overflow-y: auto">
                  <div
                    v-for="(item, idx) in testResult.results"
                    :key="idx"
                    style="margin-bottom: 8px; padding: 8px; background: #f5f7fa; border-radius: 4px; font-size: 12px"
                  >
                    <div v-for="(val, key) in item" :key="key" style="margin-bottom: 2px">
                      <span style="color: #409eff; font-weight: bold">{{ key }}:</span>
                      <span style="color: #303133; word-break: break-all">
                        {{ typeof val === 'string' && val.length > 150 ? val.slice(0, 150) + '...' : val }}
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              <el-empty v-if="!testResult && !testError && !testing" description="选择类型后执行测试" :image-size="40" />
            </div>
          </el-col>
        </el-row>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { rulesApi, type RuleMeta, type TestResult } from '@/api/rules'

// Rule list
const ruleList = ref<RuleMeta[]>([])
const activeRule = ref('')
const jsonText = ref('')
const saving = ref(false)
const saveMsg = ref('')
const saveMsgType = ref<'success' | 'danger'>('success')

// Test panel
const testSection = ref('search')
const testKeyword = ref('凡人修仙传')
const testUrl = ref('')
const testBookId = ref('')
const testing = ref(false)
const testResult = ref<TestResult | null>(null)
const testError = ref('')

// Load
async function loadRules() {
  try {
    ruleList.value = await rulesApi.list()
  } catch (e) {
    console.error(e)
  }
}

async function selectRule(name: string) {
  activeRule.value = name
  saveMsg.value = ''
  try {
    const data = await rulesApi.get(name)
    jsonText.value = JSON.stringify(data, null, 2)
  } catch (e) {
    ElMessage.error('加载规则失败')
  }
}

function createNew() {
  activeRule.value = 'new_source'
  jsonText.value = JSON.stringify({
    source_name: 'new_source',
    base_url: 'https://example.com',
    description: '新采集规则',
    version: '1.0',
    selectors: {
      search: { url: '', container: '', fields: {} },
      novel_info: { url: '', container: '', fields: {} },
      catalog: { url: '', container: '', fields: {} },
      chapter: { url: '', container: '', fields: {} },
    },
    options: { request_delay: 1.0, timeout: 60 },
  }, null, 2)
}

function formatJson() {
  try {
    const parsed = JSON.parse(jsonText.value)
    jsonText.value = JSON.stringify(parsed, null, 2)
  } catch {
    ElMessage.warning('JSON 格式错误，无法格式化')
  }
}

async function saveRule() {
  if (!activeRule.value) return
  saving.value = true
  saveMsg.value = ''
  try {
    const data = JSON.parse(jsonText.value)
    const name = data.source_name || activeRule.value
    await rulesApi.save(name, data)
    activeRule.value = name
    saveMsg.value = '保存成功'
    saveMsgType.value = 'success'
    await loadRules()
  } catch (e: any) {
    saveMsg.value = e.response?.data?.detail || '保存失败'
    saveMsgType.value = 'danger'
  } finally {
    saving.value = false
    setTimeout(() => (saveMsg.value = ''), 3000)
  }
}

async function deleteCurrentRule() {
  if (!activeRule.value) return
  try {
    await rulesApi.delete(activeRule.value)
    ElMessage.success('规则已删除')
    activeRule.value = ''
    jsonText.value = ''
    loadRules()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

async function runTest() {
  if (!activeRule.value) {
    ElMessage.warning('请先选择一个规则')
    return
  }
  testing.value = true
  testResult.value = null
  testError.value = ''

  try {
    const result = await rulesApi.test({
      source_name: activeRule.value,
      section: testSection.value as any,
      test_url: testUrl.value || undefined,
      keyword: testKeyword.value || undefined,
      book_id: testBookId.value || undefined,
      chapter_url: testUrl.value || undefined,
    })
    testResult.value = result
  } catch (e: any) {
    testError.value = e.response?.data?.detail || String(e)
  } finally {
    testing.value = false
  }
}

onMounted(loadRules)
</script>
