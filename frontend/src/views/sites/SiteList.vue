<template>
  <div>
    <div class="page-header">
      <h2>🌐 站群管理</h2>
      <p>多站点管理 · 域名绑定 · 伪静态 · 章节分页 · 链轮配置</p>
    </div>

    <div class="content-card" style="margin-bottom:16px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
        <div style="display:flex;align-items:center;gap:12px">
          <strong>站点列表</strong>
          <el-button v-if="selectedIds.length > 0" size="small" type="danger" @click="batchDelete">
            批量删除 ({{ selectedIds.length }})
          </el-button>
        </div>
        <el-button type="primary" size="small" @click="openDialog()">+ 添加站点</el-button>
      </div>

      <el-table :data="sites" stripe v-loading="loading" @selection-change="onSelectionChange" ref="tableRef">
        <el-table-column type="selection" width="40"/>
        <el-table-column prop="name" label="站点名称" width="140"/>
        <el-table-column prop="domain" label="域名" width="200"/>
        <el-table-column prop="template" label="模板" width="110">
          <template #default="{row}">
            <el-tag size="small" :type="templateColor(row.template)">{{ row.template }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="伪静态" width="90">
          <template #default="{row}">
            <el-tag size="small" :type="row.url_patterns?'success':'info'">{{ row.url_patterns?'自定义':'默认' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="分页" width="70">
          <template #default="{row}">
            <el-tag size="small" :type="row.chapter_pagination?.enabled?'success':'info'">
              {{ row.chapter_pagination?.enabled?'开启':'关闭' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="offset" label="偏移" width="65"/>
        <el-table-column prop="is_active" label="状态" width="70">
          <template #default="{row}">
            <el-tag size="small" :type="row.is_active?'success':'info'">{{ row.is_active?'启用':'禁用' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="描述" min-width="120"/>
        <el-table-column label="操作" width="140">
          <template #default="{row}">
            <el-button link size="small" type="primary" @click="openDialog(row)">编辑</el-button>
            <el-popconfirm title="删除?" @confirm="deleteSite(row.id)">
              <template #reference><el-button link size="small" type="danger">删除</el-button></template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- Add/Edit Dialog with Tabs -->
    <el-dialog v-model="showDialog" :title="editing?'编辑站点':'添加站点'" width="750px" destroy-on-close>
      <el-tabs v-model="activeTab" type="border-card">
        <!-- Tab 1: Basic Info -->
        <el-tab-pane label="基本信息" name="basic">
          <el-form :model="form" label-width="80px">
            <el-form-item label="站点名称"><el-input v-model="form.name" placeholder="如：笔趣阁"/></el-form-item>
            <el-form-item label="域名"><el-input v-model="form.domain" placeholder="如：novel.example.com"/></el-form-item>
            <el-form-item label="模板">
              <el-select v-model="form.template" style="width:100%">
                <el-option label="default (默认)" value="default"/>
                <el-option label="biquge (笔趣阁·红)" value="biquge"/>
                <el-option label="teezi (提子·绿)" value="teezi"/>
                <el-option label="quanben5 (全本·蓝)" value="quanben5"/>
                <el-option label="xiangshu (香书·橙)" value="xiangshu"/>
                <el-option label="qudu (趣读·紫)" value="qudu"/>
                <el-option label="daquan (大全·金)" value="daquan"/>
              </el-select>
            </el-form-item>
            <el-form-item label="偏移量"><el-input-number v-model="form.offset" :min="0" :max="99999"/></el-form-item>
            <el-form-item label="语言">
              <el-select v-model="form.language" style="width:100%">
                <el-option v-for="l in langOptions" :key="l.code" :label="l.name" :value="l.code"/>
              </el-select>
            </el-form-item>
            <el-form-item label="翻译功能"><el-switch v-model="form.translate_enabled"/></el-form-item>
            <el-form-item label="启用"><el-switch v-model="form.is_active"/></el-form-item>
            <el-form-item label="描述"><el-input v-model="form.description" type="textarea" :rows="2"/></el-form-item>
          </el-form>
        </el-tab-pane>

        <!-- Tab 2: Pseudo-static URLs -->
        <el-tab-pane label="🔗 伪静态" name="url_patterns">
          <el-alert type="info" :closable="false" show-icon style="margin-bottom:12px">
            <template #title>使用 <code>{'{id}'}</code> <code>{'{keyword}'}</code> 等占位符定义URL格式。留空使用默认。</template>
          </el-alert>
          <el-form label-width="110px">
            <el-form-item label="小说详情页">
              <el-input v-model="form.url_patterns.novel_detail" placeholder="/novel/{id}/"/>
              <div style="font-size:11px;color:#909399;margin-top:2px">默认: /novel/{'{id}'}/</div>
            </el-form-item>
            <el-form-item label="章节目录页">
              <el-input v-model="form.url_patterns.chapter_list" placeholder="/novel/{id}/chapters/"/>
            </el-form-item>
            <el-form-item label="章节阅读页">
              <el-input v-model="form.url_patterns.chapter_read" placeholder="/chapter/{id}.html"/>
              <div style="font-size:11px;color:#909399;margin-top:2px">常用: /chapter/{'{id}'}.html 或 /read/{'{id}'}/</div>
            </el-form-item>
            <el-form-item label="分类列表页">
              <el-input v-model="form.url_patterns.category_list" placeholder="/category/{id}/"/>
            </el-form-item>
            <el-form-item label="搜索页">
              <el-input v-model="form.url_patterns.search" placeholder="/search/{keyword}/"/>
            </el-form-item>
            <el-form-item label="">
              <el-button size="small" @click="resetUrlPatterns">恢复默认</el-button>
              <el-button size="small" type="primary" @click="presetUrl('html')">.html 预设</el-button>
              <el-button size="small" type="primary" @click="presetUrl('dir')">目录式预设</el-button>
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <!-- Tab 3: Chapter Pagination -->
        <el-tab-pane label="📄 章节分页" name="pagination">
          <el-form label-width="110px">
            <el-form-item label="启用分页">
              <el-switch v-model="form.chapter_pagination.enabled"/>
            </el-form-item>
            <template v-if="form.chapter_pagination.enabled">
              <el-form-item label="分页方式">
                <el-radio-group v-model="form.chapter_pagination.method">
                  <el-radio value="word_count">按字数分页</el-radio>
                  <el-radio value="page_count">按固定页数</el-radio>
                </el-radio-group>
              </el-form-item>
              <el-form-item v-if="form.chapter_pagination.method==='word_count'" label="每页字数">
                <el-input-number v-model="form.chapter_pagination.words_per_page" :min="500" :max="10000" :step="500"/>
                <span style="margin-left:8px;color:#909399;font-size:12px">推荐 2000-5000</span>
              </el-form-item>
              <el-form-item v-else label="固定页数">
                <el-input-number v-model="form.chapter_pagination.pages_per_chapter" :min="2" :max="10"/>
                <span style="margin-left:8px;color:#909399;font-size:12px">每章平均分成N页</span>
              </el-form-item>
              <el-form-item label="页码参数名">
                <el-input v-model="form.chapter_pagination.page_param" placeholder="page" style="width:120px"/>
              </el-form-item>
              <el-form-item label="首页不带参数">
                <el-switch v-model="form.chapter_pagination.canonical_first_page"/>
                <span style="margin-left:8px;color:#909399;font-size:12px">首页不含 ?page= 参数，有利于SEO</span>
              </el-form-item>
            </template>
          </el-form>
        </el-tab-pane>

        <!-- Tab 4: Link Wheel -->
        <el-tab-pane label="🔄 链轮" name="link_wheel">
          <el-form label-width="110px">
            <el-form-item label="启用链轮">
              <el-switch v-model="form.link_wheel.enabled"/>
            </el-form-item>
            <template v-if="form.link_wheel.enabled">
              <el-form-item label="每页最多链接">
                <el-input-number v-model="form.link_wheel.max_links_per_page" :min="1" :max="50"/>
              </el-form-item>
              <el-form-item label="展示位置">
                <el-select v-model="form.link_wheel.link_section" style="width:150px">
                  <el-option label="侧边栏" value="sidebar"/>
                  <el-option label="页脚" value="footer"/>
                  <el-option label="正文内嵌" value="inline"/>
                </el-select>
              </el-form-item>
              <el-form-item label="新窗口打开">
                <el-switch v-model="form.link_wheel.open_new_tab"/>
              </el-form-item>
              <el-form-item label="nofollow">
                <el-switch v-model="form.link_wheel.nofollow"/>
              </el-form-item>
              <el-divider/>
              <div style="color:#909399;font-size:12px">
                链轮的详细规则（站间/站内/指定书名）请在「链轮管理」页面配置。
              </div>
            </template>
          </el-form>
        </el-tab-pane>

        <!-- Tab 5: Recommend Modules -->
        <el-tab-pane label="🎯 推荐模块" name="recommend">
          <el-alert type="info" :closable="false" show-icon style="margin-bottom:12px">
            <template #title>控制各页面推荐模块的显示与隐藏。未配置的模块默认启用。</template>
          </el-alert>
          <div class="module-page" v-for="page in modulePages" :key="page.key">
            <h4 style="margin:12px 0 8px;padding-bottom:4px;border-bottom:1px solid #ebeef5">
              {{ page.icon }} {{ page.label }}
            </h4>
            <el-row :gutter="12">
              <el-col :span="8" v-for="mod in page.modules" :key="mod.key">
                <div style="display:flex;align-items:center;justify-content:space-between;padding:6px 10px;background:#fafbfc;border-radius:6px;margin-bottom:6px">
                  <span style="font-size:13px">{{ mod.icon }} {{ mod.label }}</span>
                  <el-switch
                    size="small"
                    :model-value="getModuleEnabled(page.key, mod.key)"
                    @update:model-value="(v: boolean) => setModuleEnabled(page.key, mod.key, v)"
                  />
                </div>
                <div v-if="mod.extra" style="padding:0 10px 6px;font-size:11px;color:#909399">
                  <el-input-number
                    v-if="mod.extra === 'count'"
                    size="small"
                    :model-value="getModuleConfig(page.key, mod.key, 'count', mod.defaultCount||5)"
                    @update:model-value="(v: number|null) => setModuleConfig(page.key, mod.key, 'count', v||5)"
                    :min="1" :max="50"
                    style="width:100%"
                  />
                  <span v-else>{{ mod.extra }}</span>
                </div>
              </el-col>
            </el-row>
          </div>
        </el-tab-pane>
      </el-tabs>
      <template #footer>
        <el-button @click="showDialog=false">取消</el-button>
        <el-button type="primary" @click="saveSite">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { sitesApi, type SiteRecord } from '@/api/sites'

const sites = ref<SiteRecord[]>([])
const loading = ref(false)
const showDialog = ref(false)
const editing = ref(false)
const activeTab = ref('basic')
const selectedIds = ref<string[]>([])

function onSelectionChange(rows: SiteRecord[]) {
  selectedIds.value = rows.map((r) => r.id)
}

async function batchDelete() {
  try {
    await ElMessageBox.confirm(
      `确定删除选中的 ${selectedIds.value.length} 个站点吗？此操作不可逆。`,
      '批量删除确认',
      { type: 'warning', confirmButtonText: '确定删除', cancelButtonText: '取消' }
    )
    await sitesApi.batchDelete(selectedIds.value)
    ElMessage.success(`已删除 ${selectedIds.value.length} 个站点`)
    selectedIds.value = []
    loadSites()
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

const langOptions = [
  {code:'zh',name:'中文'},{code:'en',name:'English'},{code:'ja',name:'日本語'},
  {code:'ko',name:'한국어'},{code:'fr',name:'Français'},{code:'de',name:'Deutsch'},
  {code:'es',name:'Español'},{code:'pt',name:'Português'},{code:'ru',name:'Русский'},
  {code:'ar',name:'العربية'},{code:'th',name:'ภาษาไทย'},{code:'vi',name:'Tiếng Việt'},
  {code:'id',name:'Bahasa Indonesia'},{code:'it',name:'Italiano'},{code:'tr',name:'Türkçe'},
  {code:'hi',name:'हिन्दी'},{code:'fa',name:'فارسی'},
  {code:'cs',name:'Čeština'},{code:'da',name:'Dansk'},{code:'nl',name:'Nederlands'},
  {code:'fi',name:'Suomi'},{code:'el',name:'Ελληνικά'},{code:'he',name:'עברית'},
  {code:'hu',name:'Magyar'},{code:'ga',name:'Gaeilge'},{code:'pl',name:'Polski'},
  {code:'sk',name:'Slovenčina'},{code:'sv',name:'Svenska'},{code:'uk',name:'Українська'},
  {code:'az',name:'Azərbaycan'},
]

const defaultForm = () => ({
  name:'', domain:'', template:'default', offset:0, is_active:true, description:'', language:'zh', translate_enabled: true,
  url_patterns: { novel_detail:'', chapter_list:'', chapter_read:'', category_list:'', search:'' },
  chapter_pagination: { enabled:false, method:'word_count', words_per_page:3000, pages_per_chapter:3, page_param:'page', canonical_first_page:true },
  link_wheel: { enabled:false, max_links_per_page:8, link_section:'sidebar', open_new_tab:true, nofollow:false },
  recommend_modules: {} as Record<string, any>,
})

// Module pages definition
const modulePages = [
  { key: 'home', icon: '🏠', label: '首页', modules: [
    { key: 'hero_carousel', icon: '🎠', label: '轮播图' },
    { key: 'category_sections', icon: '📂', label: '分类区块', extra: 'count', defaultCount: 9 },
    { key: 'latest_updates', icon: '🕐', label: '最新更新', extra: 'count', defaultCount: 25 },
    { key: 'hot_ranking', icon: '🏆', label: '热门排行', extra: 'count', defaultCount: 15 },
    { key: 'friend_links', icon: '🔗', label: '友情链接' },
    { key: 'link_wheel', icon: '🔄', label: '链轮面包屑' },
  ]},
  { key: 'novel_detail', icon: '📖', label: '小说详情页', modules: [
    { key: 'friend_links', icon: '🔗', label: '友情链接' },
    { key: 'link_wheel', icon: '🔄', label: '链轮面包屑' },
  ]},
  { key: 'chapter_read', icon: '📄', label: '章节阅读页', modules: [
    { key: 'random_recommend', icon: '🎲', label: '随机推荐5本书', extra: 'count', defaultCount: 5 },
    { key: 'reader_toolbar', icon: '🛠', label: '阅读工具栏' },
    { key: 'link_wheel', icon: '🔄', label: '链轮侧边栏' },
  ]},
  { key: 'chapter_list', icon: '📋', label: '章节目录页', modules: [
    { key: 'link_wheel', icon: '🔄', label: '链轮面包屑' },
  ]},
  { key: 'search', icon: '🔍', label: '搜索页', modules: [
    { key: 'link_wheel', icon: '🔄', label: '链轮面包屑' },
  ]},
  { key: 'book_library', icon: '📚', label: '书库页', modules: [
    { key: 'link_wheel', icon: '🔄', label: '链轮面包屑' },
  ]},
]

function getModuleEnabled(page: string, mod: string): boolean {
  const cfg = form.recommend_modules[page]?.[mod]
  if (!cfg || cfg.enabled === undefined) return true
  return cfg.enabled
}

function setModuleEnabled(page: string, mod: string, v: boolean) {
  if (!form.recommend_modules[page]) form.recommend_modules[page] = {}
  if (!form.recommend_modules[page][mod]) form.recommend_modules[page][mod] = {}
  form.recommend_modules[page][mod].enabled = v
}

function getModuleConfig(page: string, mod: string, key: string, def: number): number {
  return form.recommend_modules[page]?.[mod]?.[key] ?? def
}

function setModuleConfig(page: string, mod: string, key: string, v: number) {
  if (!form.recommend_modules[page]) form.recommend_modules[page] = {}
  if (!form.recommend_modules[page][mod]) form.recommend_modules[page][mod] = {}
  form.recommend_modules[page][mod][key] = v
}

const form = reactive(defaultForm())
const editId = ref('')

function templateColor(t: string) {
  const m: Record<string,string> = {default:'',biquge:'danger',teezi:'success',quanben5:'',xiangshu:'warning',qudu:'',daquan:'warning'}
  return m[t] || ''
}

async function loadSites() {
  loading.value = true
  try { sites.value = await sitesApi.list() } catch (e: any) {
    console.error('Failed to load sites', e)
    ElMessage.error('加载站点列表失败')
  }
  loading.value = false
}

function openDialog(row?: any) {
  if (row) {
    editing.value = true; editId.value = row.id
    Object.assign(form, {
      name:row.name, domain:row.domain, template:row.template, language:row.language||'zh',translate_enabled:row.translate_enabled ?? true,
      offset:row.offset, is_active:row.is_active, description:row.description||'',
      url_patterns: Object.assign({novel_detail:'',chapter_list:'',chapter_read:'',category_list:'',search:''}, row.url_patterns || {}),
      chapter_pagination: Object.assign({enabled:false,method:'word_count',words_per_page:3000,pages_per_chapter:3,page_param:'page',canonical_first_page:true}, row.chapter_pagination || {}),
      link_wheel: Object.assign({enabled:false,max_links_per_page:8,link_section:'sidebar',open_new_tab:true,nofollow:false}, row.link_wheel || {}),
      recommend_modules: row.recommend_modules ? JSON.parse(JSON.stringify(row.recommend_modules)) : {},
    })
  } else {
    editing.value = false; editId.value = ''
    Object.assign(form, defaultForm())
  }
  activeTab.value = 'basic'
  showDialog.value = true
}

function resetUrlPatterns() {
  form.url_patterns = { novel_detail:'', chapter_list:'', chapter_read:'', category_list:'', search:'' }
}

function presetUrl(style: string) {
  if (style === 'html') {
    form.url_patterns = {
      novel_detail: '/novel/{id}.html',
      chapter_list: '/novel/{id}/chapters/',
      chapter_read: '/chapter/{id}.html',
      category_list: '/category/{id}/',
      search: '/search/{keyword}/',
    }
  } else {
    form.url_patterns = {
      novel_detail: '/book/{id}/',
      chapter_list: '/book/{id}/catalog/',
      chapter_read: '/read/{id}/',
      category_list: '/cat/{id}/',
      search: '/search/{keyword}/',
    }
  }
}

async function saveSite() {
  // Filter out empty url_patterns
  const up = { ...form }
  const hasUrlPatterns = Object.values(up.url_patterns).some((v: unknown) => v)
  if (!hasUrlPatterns) up.url_patterns = null as any

  try {
    if (editing.value) {
      await sitesApi.update(editId.value, up)
      ElMessage.success('已更新')
    } else {
      await sitesApi.create(up)
      ElMessage.success('已创建')
    }
    showDialog.value = false; loadSites()
  } catch (e: any) { ElMessage.error(e.response?.data?.detail || '保存失败') }
}

async function deleteSite(id: string) {
  try { await sitesApi.delete(id); ElMessage.success('已删除'); loadSites() }
  catch (e: any) { ElMessage.error('删除失败') }
}

onMounted(loadSites)
</script>
