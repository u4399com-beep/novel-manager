<template>
  <div class="rule-editor">
    <div class="page-header">
      <h2>🕷️ 采集规则编辑器</h2>
      <p>可视化编辑爬虫规则 · 在线测试 · 多站规则管理</p>
    </div>

    <div class="rule-layout">
      <!-- ====== LEFT: Rule List ====== -->
      <aside class="rule-sidebar">
        <div class="sidebar-header">
          <strong>规则列表</strong>
          <el-button size="small" type="primary" @click="createNew">+ 新建</el-button>
        </div>

        <div class="rule-list" v-if="ruleList.length">
          <div
            v-for="rule in ruleList"
            :key="rule.source_name"
            class="rule-item"
            :class="{ active: activeRule === rule.source_name }"
            @click="selectRule(rule.source_name)"
          >
            <div class="rule-item-main">
              <span class="rule-name">{{ rule.source_name }}</span>
              <span class="rule-ver">v{{ rule.version }}</span>
            </div>
            <div class="rule-item-desc">{{ rule.description }}</div>
            <div class="rule-item-url">{{ rule.base_url }}</div>
          </div>
        </div>
        <el-empty v-else description="暂无规则" :image-size="48" />

        <!-- Quick Templates -->
        <div class="template-section">
          <div class="sidebar-header">
            <strong>📄 模板片段</strong>
          </div>
          <div class="template-list">
            <div class="template-item" @click="insertTemplate('search')">
              <span class="tpl-icon">🔍</span>
              <div>
                <div class="tpl-name">搜索选择器</div>
                <div class="tpl-desc">search 字段模板</div>
              </div>
            </div>
            <div class="template-item" @click="insertTemplate('novel_info')">
              <span class="tpl-icon">📖</span>
              <div>
                <div class="tpl-name">小说信息选择器</div>
                <div class="tpl-desc">novel_info 字段模板</div>
              </div>
            </div>
            <div class="template-item" @click="insertTemplate('catalog')">
              <span class="tpl-icon">📋</span>
              <div>
                <div class="tpl-name">目录选择器</div>
                <div class="tpl-desc">catalog 字段模板</div>
              </div>
            </div>
            <div class="template-item" @click="insertTemplate('chapter')">
              <span class="tpl-icon">📄</span>
              <div>
                <div class="tpl-name">章节选择器</div>
                <div class="tpl-desc">chapter 字段模板</div>
              </div>
            </div>
          </div>
        </div>
      </aside>

      <!-- ====== RIGHT: Editor + Test ====== -->
      <main class="rule-main">
        <!-- Toolbar -->
        <div class="toolbar">
          <div class="toolbar-left">
            <span class="toolbar-title" v-if="activeRule">
              <el-tag :type="isModified ? 'warning' : 'success'" size="small" effect="dark">
                {{ isModified ? '● 已修改' : '✓ 已保存' }}
              </el-tag>
              <strong>{{ activeRule }}</strong>
            </span>
            <span class="toolbar-title" v-else style="color:#909399">← 选择或新建一个规则</span>
          </div>
          <div class="toolbar-right">
            <span class="hint">Ctrl+S 保存</span>
            <el-button size="small" @click="formatJson">🔧 格式化</el-button>
            <el-button size="small" type="primary" @click="saveRule" :loading="saving" :disabled="!activeRule">
              💾 保存
            </el-button>
            <el-popconfirm title="确定删除此规则？此操作不可逆" @confirm="deleteCurrentRule" v-if="activeRule">
              <template #reference>
                <el-button size="small" type="danger" :disabled="!activeRule">🗑 删除</el-button>
              </template>
            </el-popconfirm>
          </div>
        </div>

        <div class="editor-test-grid">
          <!-- JSON Editor -->
          <div class="json-panel">
            <div class="panel-header">
              <strong>📝 规则 JSON</strong>
              <el-button-group size="small">
                <el-button size="small" @click="zoomOut" :disabled="fontSize <= 10">A-</el-button>
                <el-button size="small" @click="zoomIn" :disabled="fontSize >= 18">A+</el-button>
              </el-button-group>
            </div>
            <div class="editor-container">
              <textarea
                ref="editorRef"
                v-model="jsonText"
                class="json-editor"
                :style="{ fontSize: fontSize + 'px' }"
                spellcheck="false"
                placeholder="在此编辑规则 JSON..."
                @keydown="onEditorKeydown"
                @input="onEditorInput"
              ></textarea>
              <!-- Simple JSON error indicator -->
              <div v-if="jsonError" class="json-error-bar">
                ⚠️ {{ jsonError }}
              </div>
            </div>
          </div>

          <!-- Test Panel -->
          <div class="test-panel">
            <div class="panel-header">
              <strong>🧪 在线测试</strong>
              <span v-if="activeRule" style="font-size:11px;color:#909399">{{ activeRule }}</span>
            </div>

            <!-- Section Tabs -->
            <div class="test-tabs">
              <button
                v-for="s in testSections"
                :key="s.value"
                class="test-tab"
                :class="{ active: testSection === s.value }"
                @click="testSection = s.value"
              >
                {{ s.icon }} {{ s.label }}
              </button>
            </div>

            <!-- Test Inputs -->
            <div class="test-inputs">
              <template v-if="testSection === 'search'">
                <el-input v-model="testKeyword" placeholder="搜索关键词" size="small">
                  <template #prepend>关键词</template>
                </el-input>
              </template>
              <template v-else-if="testSection === 'novel_info'">
                <el-input v-model="testUrl" placeholder="如：https://www.23qb.net/book/4262/" size="small">
                  <template #prepend>URL</template>
                </el-input>
              </template>
              <template v-else-if="testSection === 'catalog'">
                <el-input v-model="testBookId" placeholder="如：11928" size="small">
                  <template #prepend>Book ID</template>
                </el-input>
              </template>
              <template v-else-if="testSection === 'chapter'">
                <el-input v-model="testUrl" placeholder="如：https://www.23qb.net/book/4262/12345.html" size="small">
                  <template #prepend>URL</template>
                </el-input>
              </template>

              <el-button type="primary" :loading="testing" @click="runTest" size="small" style="width:100%">
                ▶ {{ testing ? '测试中...' : '执行测试' }}
              </el-button>
            </div>

            <!-- Test Results -->
            <div class="test-results" v-if="testError">
              <div class="test-error">❌ {{ testError }}</div>
            </div>

            <div class="test-results" v-else-if="testResult">
              <div class="test-meta">
                <el-tag type="success" size="small">✅ {{ testResult.total || 0 }} 条结果</el-tag>
                <el-tag size="small" v-if="testResult.url" style="margin-left:4px">
                  <a :href="testResult.url" target="_blank" style="text-decoration:none;color:inherit">
                    🔗 {{ testResult.url.length > 50 ? testResult.url.slice(0, 50) + '...' : testResult.url }}
                  </a>
                </el-tag>
              </div>

              <div class="result-cards">
                <div
                  v-for="(item, idx) in testResult.results"
                  :key="idx"
                  class="result-card"
                >
                  <div class="result-card-header">
                    <el-tag size="small" type="info">#{{ idx + 1 }}</el-tag>
                    <span v-if="item.title" class="result-title">{{ item.title }}</span>
                  </div>
                  <table class="result-fields">
                    <tr v-for="(val, key) in item" :key="key">
                      <td class="field-key">{{ key }}</td>
                      <td class="field-val" :title="typeof val === 'string' ? val : ''">
                        <template v-if="typeof val === 'string' && val.length > 120">
                          <span class="truncated">{{ val.slice(0, 120) }}...</span>
                          <el-button link size="small" @click="showFullValue(key, val)">展开</el-button>
                        </template>
                        <template v-else>
                          {{ typeof val === 'object' ? JSON.stringify(val) : String(val) }}
                        </template>
                      </td>
                    </tr>
                  </table>
                </div>
              </div>
            </div>

            <el-empty
              v-if="!testResult && !testError && !testing"
              description="选择测试类型，填写参数后点击「执行测试」"
              :image-size="48"
            />

            <!-- Test History -->
            <div v-if="testHistory.length" class="test-history">
              <div class="panel-header" style="margin-top:8px">
                <strong>🕐 测试记录</strong>
                <el-button link size="small" @click="testHistory = []">清空</el-button>
              </div>
              <div
                v-for="(h, i) in testHistory.slice(0, 5)"
                :key="i"
                class="history-item"
                @click="replayTest(h)"
              >
                <span :style="{ color: h.error ? '#f56c6c' : '#67c23a' }">
                  {{ h.error ? '❌' : '✅' }}
                </span>
                <span class="hist-section">{{ h.section }}</span>
                <span class="hist-time">{{ h.time }}</span>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>

    <!-- Full Value Dialog -->
    <el-dialog v-model="showDialog" :title="dialogKey" width="700px">
      <div style="max-height:500px;overflow-y:auto;white-space:pre-wrap;font-size:14px;line-height:1.8">
        {{ dialogValue }}
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { rulesApi, type RuleMeta, type TestResult } from '@/api/rules'

// --- Rule List ---
const ruleList = ref<RuleMeta[]>([])
const activeRule = ref('')
const jsonText = ref('')
const originalJson = ref('')
const jsonError = ref('')
const isModified = ref(false)
const saving = ref(false)
const editorRef = ref<HTMLTextAreaElement | null>(null)
const fontSize = ref(13)

// --- Test Panel ---
const testSections = [
  { value: 'search', label: '搜索', icon: '🔍' },
  { value: 'novel_info', label: '小说信息', icon: '📖' },
  { value: 'catalog', label: '目录', icon: '📋' },
  { value: 'chapter', label: '章节', icon: '📄' },
]
const testSection = ref('search')
const testKeyword = ref('凡人修仙传')
const testUrl = ref('')
const testBookId = ref('')
const testing = ref(false)
const testResult = ref<TestResult | null>(null)
const testError = ref('')
const testHistory = ref<{ section: string; time: string; error?: string }[]>([])

// --- Dialog ---
const showDialog = ref(false)
const dialogKey = ref('')
const dialogValue = ref('')

// --- Computed ---
function onEditorInput() {
  const mod = jsonText.value !== originalJson.value
  isModified.value = mod
  // Validate JSON
  try {
    JSON.parse(jsonText.value)
    jsonError.value = ''
  } catch (e: any) {
    jsonError.value = e.message
  }
}

function onEditorKeydown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key === 's') {
    e.preventDefault()
    saveRule()
  }
  // Tab key -> 2 spaces
  if (e.key === 'Tab') {
    e.preventDefault()
    const ta = e.target as HTMLTextAreaElement
    const start = ta.selectionStart
    const end = ta.selectionEnd
    jsonText.value = jsonText.value.substring(0, start) + '  ' + jsonText.value.substring(end)
    nextTick(() => {
      ta.selectionStart = ta.selectionEnd = start + 2
    })
  }
}

function zoomIn() { fontSize.value = Math.min(18, fontSize.value + 1) }
function zoomOut() { fontSize.value = Math.max(10, fontSize.value - 1) }

// --- Rule CRUD ---
async function loadRules() {
  try { ruleList.value = await rulesApi.list() } catch (e: any) {
    console.error('Failed to load rules', e)
    ElMessage.error('加载规则列表失败')
  }
}

async function selectRule(name: string) {
  if (isModified.value) {
    try { await ElMessageBox.confirm('当前规则有未保存的修改，是否放弃？', '提示', { type: 'warning' }) }
    catch { return }
  }
  activeRule.value = name
  isModified.value = false
  jsonError.value = ''
  try {
    const data = await rulesApi.get(name)
    const text = JSON.stringify(data, null, 2)
    jsonText.value = text
    originalJson.value = text
  } catch { ElMessage.error('加载规则失败') }
}

function createNew() {
  if (isModified.value) {
    ElMessageBox.confirm('当前规则有未保存的修改，是否放弃？', '提示', { type: 'warning' }).then(() => _createNew()).catch(() => {})
  } else {
    _createNew()
  }
}

function _createNew() {
  activeRule.value = 'new_source'
  const template = {
    source_name: 'new_source',
    base_url: 'https://example.com',
    description: '新采集规则',
    version: '1.0',
    selectors: {
      search: { url: '/search?q={keyword}', container: '.search-item', fields: {
        title: { selector: 'a.title', attribute: 'text' },
        author: { selector: '.author', attribute: 'text' },
        url: { selector: 'a.title', attribute: 'href', transform: 'absolute_url' },
      }},
      novel_info: { container: '', fields: {
        title: { selector: 'h1', attribute: 'text' },
        author: { selector: '.author', attribute: 'text' },
        description: { selector: '.desc', attribute: 'text' },
        cover_url: { selector: '.cover img', attribute: 'src', transform: 'absolute_url' },
      }},
      catalog: { container: '.chapter-item', fields: {
        title: { selector: 'a', attribute: 'text' },
        url: { selector: 'a', attribute: 'href', transform: 'absolute_url' },
      }},
      chapter: { container: '', fields: {
        title: { selector: 'h1', attribute: 'text' },
        content: { selector: '.content', attribute: 'text' },
      }},
    },
    options: { request_delay: 1.0, timeout: 60 },
    cleaner: { enabled: false, remove_lines: [], inline_remove: [], min_line_length: 2 },
  }
  const text = JSON.stringify(template, null, 2)
  jsonText.value = text
  originalJson.value = text
  isModified.value = false
  jsonError.value = ''
}

function formatJson() {
  try {
    const parsed = JSON.parse(jsonText.value)
    jsonText.value = JSON.stringify(parsed, null, 2)
    jsonError.value = ''
    ElMessage.success('已格式化')
  } catch { ElMessage.warning('JSON 格式错误，无法格式化') }
}

async function saveRule() {
  if (!activeRule.value) return
  saving.value = true
  try {
    const data = JSON.parse(jsonText.value)
    const name = data.source_name || activeRule.value
    await rulesApi.save(name, data)
    activeRule.value = name
    originalJson.value = jsonText.value
    isModified.value = false
    jsonError.value = ''
    ElMessage.success(`规则 "${name}" 已保存`)
    await loadRules()
  } catch (e: any) {
    if (e instanceof SyntaxError) {
      ElMessage.error('JSON 格式错误，请先修正再保存')
    } else {
      ElMessage.error(e.response?.data?.detail || '保存失败')
    }
  } finally {
    saving.value = false
  }
}

async function deleteCurrentRule() {
  if (!activeRule.value) return
  try {
    await rulesApi.delete(activeRule.value)
    ElMessage.success('规则已删除')
    activeRule.value = ''
    jsonText.value = ''
    originalJson.value = ''
    isModified.value = false
    loadRules()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

// --- Template Snippets ---
function insertTemplate(section: string) {
  const templates: Record<string, any> = {
    search: { url: '/search?keyword={keyword}', container: '.search-result-item', fields: {
      title: { selector: '.result-title a', attribute: 'text' },
      author: { selector: '.result-author', attribute: 'text' },
      url: { selector: '.result-title a', attribute: 'href', transform: 'absolute_url' },
      description: { selector: '.result-desc', attribute: 'text', fallback: '' },
    }},
    novel_info: { container: 'body', fields: {
      title: { selector: 'meta[property="og:novel:book_name"]', attribute: 'content', fallback_selector: 'h1', fallback_attribute: 'text' },
      author: { selector: 'meta[property="og:novel:author"]', attribute: 'content', fallback_selector: '.author', fallback_attribute: 'text' },
      description: { selector: 'meta[property="og:description"]', attribute: 'content', fallback_selector: '.description', fallback_attribute: 'text' },
      cover_url: { selector: 'meta[property="og:image"]', attribute: 'content', transform: 'absolute_url' },
      status: { selector: 'meta[property="og:novel:status"]', attribute: 'content', transform: 'status_map' },
    }},
    catalog: { container: '.chapter-list a', fields: {
      title: { selector: '', attribute: 'text' },
      url: { selector: '', attribute: 'href', transform: 'absolute_url' },
    }},
    chapter: { container: 'body', fields: {
      title: { selector: 'h1', attribute: 'text' },
      content: { selector: '.article-content', attribute: 'text', cleanup: ['script', 'ins', '.adsbygoogle'] },
    }},
  }

  ElMessageBox.confirm(
    `将在当前规则的 selectors.${section} 中插入模板字段，是否继续？`,
    '插入模板',
    { type: 'info', confirmButtonText: '插入', cancelButtonText: '取消' }
  ).then(() => {
    try {
      const data = JSON.parse(jsonText.value)
      if (!data.selectors) data.selectors = {}
      data.selectors[section] = templates[section]
      jsonText.value = JSON.stringify(data, null, 2)
      isModified.value = true
      ElMessage.success(`已插入 ${section} 模板`)
    } catch {
      ElMessage.error('当前 JSON 格式错误，请先修正')
    }
  }).catch(() => {})
}

// --- Testing ---
async function runTest() {
  if (!activeRule.value) { ElMessage.warning('请先选择一个规则'); return }
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
    testHistory.value.unshift({
      section: testSection.value,
      time: new Date().toLocaleTimeString('zh-CN'),
    })
    if (testHistory.value.length > 20) testHistory.value.pop()
  } catch (e: any) {
    testError.value = e.response?.data?.detail || String(e)
    testHistory.value.unshift({
      section: testSection.value,
      time: new Date().toLocaleTimeString('zh-CN'),
      error: testError.value,
    })
  } finally {
    testing.value = false
  }
}

function replayTest(h: any) {
  testSection.value = h.section
  runTest()
}

function showFullValue(key: string, val: string) {
  dialogKey.value = key
  dialogValue.value = val
  showDialog.value = true
}

// --- Keyboard shortcut ---
function onGlobalKeydown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key === 's') {
    // Only handle if not already caught by editor textarea
    if (document.activeElement?.tagName !== 'TEXTAREA') {
      e.preventDefault()
      saveRule()
    }
  }
}

onMounted(() => {
  loadRules()
  document.addEventListener('keydown', onGlobalKeydown)
})
onUnmounted(() => {
  document.removeEventListener('keydown', onGlobalKeydown)
})
</script>

<style scoped>
.rule-editor { height: calc(100vh - 100px); display: flex; flex-direction: column; }

.rule-layout { display: flex; gap: 12px; flex: 1; min-height: 0; }

/* ---- Sidebar ---- */
.rule-sidebar {
  width: 240px; flex-shrink: 0; display: flex; flex-direction: column; gap: 8px;
  overflow-y: auto;
}
.sidebar-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 8px 0; margin-bottom: 4px;
}
.rule-list { display: flex; flex-direction: column; gap: 2px; }
.rule-item {
  padding: 10px 12px; border-radius: 6px; cursor: pointer; transition: all .15s;
  border: 1px solid transparent; background: #fff;
}
.rule-item:hover { background: #f0f5ff; border-color: #d6e4ff; }
.rule-item.active { background: #e6f0ff; border-color: #409eff; }
.rule-item-main { display: flex; align-items: center; gap: 6px; margin-bottom: 2px; }
.rule-name { font-weight: 600; font-size: 13px; color: #303133; }
.rule-ver { font-size: 10px; color: #909399; background: #f0f2f5; padding: 1px 5px; border-radius: 3px; }
.rule-item-desc { font-size: 11px; color: #909399; }
.rule-item-url { font-size: 10px; color: #c0c4cc; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* ---- Templates ---- */
.template-section { margin-top: 8px; }
.template-list { display: flex; flex-direction: column; gap: 2px; }
.template-item {
  display: flex; align-items: center; gap: 8px; padding: 8px 10px;
  border-radius: 6px; cursor: pointer; transition: all .15s; background: #fafafa;
}
.template-item:hover { background: #f0f5ff; }
.tpl-icon { font-size: 18px; }
.tpl-name { font-size: 12px; font-weight: 500; color: #303133; }
.tpl-desc { font-size: 10px; color: #c0c4cc; }

/* ---- Main ---- */
.rule-main { flex: 1; display: flex; flex-direction: column; min-width: 0; gap: 8px; }

.toolbar {
  display: flex; justify-content: space-between; align-items: center;
  padding: 6px 12px; background: #fff; border-radius: 8px; border: 1px solid #ebeef5;
}
.toolbar-left, .toolbar-right { display: flex; align-items: center; gap: 8px; }
.toolbar-title { display: flex; align-items: center; gap: 8px; font-size: 13px; }
.hint { font-size: 11px; color: #c0c4cc; }

.editor-test-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 12px; flex: 1; min-height: 0;
}

/* ---- JSON Panel ---- */
.json-panel, .test-panel {
  display: flex; flex-direction: column;
  background: #fff; border-radius: 8px; border: 1px solid #ebeef5; overflow: hidden;
}
.panel-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 8px 12px; border-bottom: 1px solid #ebeef5; font-size: 13px;
}
.editor-container { flex: 1; display: flex; flex-direction: column; min-height: 0; }
.json-editor {
  flex: 1; width: 100%; border: none; resize: none; outline: none; padding: 12px;
  font-family: 'SF Mono', 'Menlo', 'Monaco', 'Consolas', monospace;
  line-height: 1.6; tab-size: 2; background: #fafbfc; color: #303133;
}
.json-editor:focus { background: #fff; }
.json-error-bar {
  padding: 6px 12px; background: #fef0f0; color: #f56c6c;
  font-size: 12px; border-top: 1px solid #fde2e2;
}

/* ---- Test Panel ---- */
.test-tabs { display: flex; border-bottom: 1px solid #ebeef5; }
.test-tab {
  flex: 1; padding: 8px 4px; border: none; background: none; cursor: pointer;
  font-size: 12px; color: #909399; transition: all .15s; border-bottom: 2px solid transparent;
}
.test-tab:hover { color: #409eff; }
.test-tab.active { color: #409eff; border-bottom-color: #409eff; font-weight: 600; }
.test-inputs { padding: 10px; display: flex; flex-direction: column; gap: 8px; }

.test-results { flex: 1; overflow-y: auto; padding: 10px; }
.test-meta { margin-bottom: 8px; display: flex; align-items: center; flex-wrap: wrap; gap: 4px; }
.test-error { color: #f56c6c; font-size: 13px; padding: 8px; background: #fef0f0; border-radius: 4px; }

.result-cards { display: flex; flex-direction: column; gap: 6px; }
.result-card {
  border: 1px solid #ebeef5; border-radius: 6px; overflow: hidden;
}
.result-card-header {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 10px; background: #fafbfc; border-bottom: 1px solid #ebeef5;
}
.result-title { font-size: 13px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.result-fields { width: 100%; border-collapse: collapse; }
.result-fields td { padding: 4px 10px; font-size: 11px; border-bottom: 1px solid #f5f7fa; }
.field-key {
  color: #409eff; font-weight: 600; width: 80px; white-space: nowrap;
  vertical-align: top; padding-top: 6px;
}
.field-val {
  color: #303133; word-break: break-all; line-height: 1.5;
  max-width: 0; /* force text-overflow in table */ ;
}
.truncated { color: #606266; }

/* ---- Test History ---- */
.test-history { border-top: 1px solid #ebeef5; padding: 8px 10px; }
.history-item {
  display: flex; align-items: center; gap: 8px; padding: 4px 8px;
  border-radius: 4px; cursor: pointer; font-size: 12px;
}
.history-item:hover { background: #f5f7fa; }
.hist-section { color: #909399; }
.hist-time { color: #c0c4cc; font-size: 11px; margin-left: auto; }
</style>
