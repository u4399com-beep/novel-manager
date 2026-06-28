<template>
  <div>
    <div class="page-header">
      <h2>🔄 链轮管理</h2>
      <p>站间链轮 · 站内书间链轮 · 跨站书链轮 · 自定义锚文本</p>
    </div>

    <div class="content-card" style="margin-bottom:16px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
        <strong>链轮列表</strong>
        <el-button type="primary" size="small" @click="openRingDialog()">+ 新建链轮</el-button>
      </div>

      <el-table :data="rings" stripe v-loading="loading">
        <el-table-column prop="name" label="名称" width="150"/>
        <el-table-column prop="ring_type" label="类型" width="130">
          <template #default="{row}">
            <el-tag size="small">{{ ringTypeLabel(row.ring_type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="范围" width="120">
          <template #default="{row}">{{ row.site_id ? '站点级' : '全局' }}</template>
        </el-table-column>
        <el-table-column prop="max_links" label="链接数" width="70"/>
        <el-table-column prop="display_mode" label="位置" width="80">
          <template #default="{row}">
            <el-tag size="small" :type="row.display_mode==='sidebar'?'':'info'">{{ row.display_mode }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="link_format" label="格式" width="100"/>
        <el-table-column label="目标数" width="80">
          <template #default="{row}">{{ row.targets?.length || 0 }}</template>
        </el-table-column>
        <el-table-column label="状态" width="70">
          <template #default="{row}">
            <el-tag size="small" :type="row.is_active?'success':'info'">{{ row.is_active?'启用':'禁用' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="240">
          <template #default="{row}">
            <el-button link size="small" type="primary" @click="openRingDialog(row)">编辑</el-button>
            <el-button link size="small" type="primary" @click="manageTargets(row)">目标({{ row.targets?.length||0 }})</el-button>
            <el-popconfirm title="删除?" @confirm="deleteRing(row.id)">
              <template #reference><el-button link size="small" type="danger">删除</el-button></template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- Ring Edit Dialog -->
    <el-dialog v-model="showRingDialog" :title="editingRing?'编辑链轮':'新建链轮'" width="650px" destroy-on-close>
      <el-form :model="ringForm" label-width="100px">
        <el-form-item label="名称"><el-input v-model="ringForm.name" placeholder="如：玄幻小说互链"/></el-form-item>
        <el-form-item label="链轮类型">
          <el-select v-model="ringForm.ring_type" style="width:100%">
            <el-option label="跨站书籍互链" value="cross_site_books"/>
            <el-option label="同站书籍互链" value="same_site_books"/>
            <el-option label="跨站(任意书)" value="cross_site"/>
            <el-option label="自定义" value="custom"/>
          </el-select>
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="每页链接数"><el-input-number v-model="ringForm.max_links" :min="1" :max="50"/></el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="展示位置">
              <el-select v-model="ringForm.display_mode">
                <el-option label="侧边栏" value="sidebar"/>
                <el-option label="页脚" value="footer"/>
                <el-option label="正文内嵌" value="inline"/>
                <el-option label="弹窗" value="popup"/>
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="站点范围">
              <el-select v-model="ringForm.site_id" clearable placeholder="全局">
                <el-option v-for="s in sites" :key="s.id" :label="s.name" :value="s.id"/>
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="链接格式">
          <el-input v-model="ringForm.link_format" placeholder="{title} - {author}"/>
          <div style="font-size:11px;color:#909399;margin-top:2px">
            可用: {'{title}'} {'{author}'} {'{site_name}'} {'{chapter}'}
          </div>
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="新窗口打开"><el-switch v-model="ringForm.open_new_tab"/></el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="nofollow"><el-switch v-model="ringForm.nofollow"/></el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="启用"><el-switch v-model="ringForm.is_active"/></el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="showRingDialog=false">取消</el-button>
        <el-button type="primary" @click="saveRing">保存</el-button>
      </template>
    </el-dialog>

    <!-- Target Management Dialog -->
    <el-dialog v-model="showTargetDialog" :title="`链轮目标 — ${targetRing?.name||''}`" width="800px" destroy-on-close>
      <div style="margin-bottom:12px;display:flex;justify-content:space-between;align-items:center">
        <span style="color:#909399;font-size:12px">每条目标定义：在哪个站的哪本书上显示 → 链接到哪个站的哪本书</span>
        <el-button size="small" type="primary" @click="openTargetDialog()">+ 添加目标</el-button>
      </div>

      <el-table :data="targets" stripe size="small" max-height="400">
        <el-table-column label="来源站" width="100">
          <template #default="{row}">{{ siteName(row.source_site_id) || '任意' }}</template>
        </el-table-column>
        <el-table-column label="来源书" width="100">
          <template #default="{row}">{{ row.source_novel_id ? row.source_novel_id.slice(0,8)+'...' : '全部' }}</template>
        </el-table-column>
        <el-table-column label="→" width="40"/>
        <el-table-column label="目标站" width="100">
          <template #default="{row}">{{ siteName(row.target_site_id) || '同站' }}</template>
        </el-table-column>
        <el-table-column label="目标书" width="100">
          <template #default="{row}">{{ row.target_novel_id ? row.target_novel_id.slice(0,8)+'...' : row.target_url?.slice(0,30)||'—' }}</template>
        </el-table-column>
        <el-table-column prop="anchor_text" label="锚文本" min-width="120"/>
        <el-table-column prop="sort_order" label="排序" width="60"/>
        <el-table-column label="操作" width="80">
          <template #default="{row}">
            <el-button link size="small" type="primary" @click="openTargetDialog(row)">编辑</el-button>
            <el-popconfirm title="删除?" @confirm="deleteTarget(row.id)">
              <template #reference><el-button link size="small" type="danger">删</el-button></template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <!-- Single Target Edit -->
    <el-dialog v-model="showSingleTarget" :title="editingTarget?'编辑目标':'添加目标'" width="550px" destroy-on-close>
      <el-form :model="targetForm" label-width="90px">
        <el-divider content-position="left">来源（链接显示在哪里）</el-divider>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="来源站点">
              <el-select v-model="targetForm.source_site_id" clearable placeholder="不限制" style="width:100%">
                <el-option v-for="s in sites" :key="s.id" :label="s.name" :value="s.id"/>
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="来源书籍ID">
              <el-input v-model="targetForm.source_novel_id" placeholder="不填=全部书籍"/>
            </el-form-item>
          </el-col>
        </el-row>

        <el-divider content-position="left">目标（链接指向哪里）</el-divider>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="目标站点">
              <el-select v-model="targetForm.target_site_id" clearable placeholder="同站" style="width:100%">
                <el-option v-for="s in sites" :key="s.id" :label="s.name" :value="s.id"/>
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="目标书籍ID">
              <el-input v-model="targetForm.target_novel_id" placeholder="书籍UUID"/>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="或直接URL">
          <el-input v-model="targetForm.target_url" placeholder="https://... 外部链接"/>
        </el-form-item>
        <el-form-item label="锚文本">
          <el-input v-model="targetForm.anchor_text" placeholder="{title} — 支持模板语法"/>
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="排序"><el-input-number v-model="targetForm.sort_order" :min="0"/></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="启用"><el-switch v-model="targetForm.is_active"/></el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="showSingleTarget=false">取消</el-button>
        <el-button type="primary" @click="saveTarget">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { sitesApi, type SiteRecord } from '@/api/sites'
import { linkRingsApi, type LinkRingRecord, type LinkRingTarget } from '@/api/linkRings'

const rings = ref<LinkRingRecord[]>([])
const sites = ref<SiteRecord[]>([])
const loading = ref(false)

// Ring dialog
const showRingDialog = ref(false)
const editingRing = ref(false)
const editRingId = ref('')
const ringForm = reactive({
  name:'', ring_type:'cross_site_books', site_id:'', max_links:5, display_mode:'sidebar',
  link_format:'{title}', open_new_tab:true, nofollow:false, is_active:true, selection_rules:null as Record<string, any> | null,
})

// Target dialog
const showTargetDialog = ref(false)
const targetRing = ref<LinkRingRecord | null>(null)
const targets = ref<LinkRingTarget[]>([])

// Single target dialog
const showSingleTarget = ref(false)
const editingTarget = ref(false)
const editTargetId = ref('')
const targetForm = reactive({
  source_site_id:'', source_novel_id:'', target_site_id:'', target_novel_id:'',
  target_url:'', anchor_text:'{title}', sort_order:0, is_active:true,
})

function ringTypeLabel(t: string) {
  const m: Record<string,string> = {cross_site_books:'跨站书链',same_site_books:'同站书链',cross_site:'跨站任意',custom:'自定义'}
  return m[t] || t
}

function siteName(id: string) {
  return sites.value.find(s => s.id === id)?.name || ''
}

async function loadRings() {
  loading.value = true
  try { rings.value = await linkRingsApi.list() } catch (e: any) {
    console.error('Failed to load rings', e)
    ElMessage.error('加载链轮列表失败')
  }
  loading.value = false
}

async function loadSites() {
  try { sites.value = await sitesApi.list() } catch (e: any) {
    console.error('Failed to load sites', e)
  }
}

// --- Ring CRUD ---
function openRingDialog(row?: any) {
  if (row) {
    editingRing.value = true; editRingId.value = row.id
    Object.assign(ringForm, {
      name:row.name, ring_type:row.ring_type, site_id:row.site_id||'',
      max_links:row.max_links, display_mode:row.display_mode, link_format:row.link_format,
      open_new_tab:row.open_new_tab, nofollow:row.nofollow, is_active:row.is_active,
      selection_rules:row.selection_rules,
    })
  } else {
    editingRing.value = false; editRingId.value = ''
    Object.assign(ringForm, {name:'',ring_type:'cross_site_books',site_id:'',max_links:5,display_mode:'sidebar',link_format:'{title}',open_new_tab:true,nofollow:false,is_active:true,selection_rules:null})
  }
  showRingDialog.value = true
}

async function saveRing() {
  try {
    if (editingRing.value) {
      await linkRingsApi.update(editRingId.value, ringForm)
      ElMessage.success('已更新')
    } else {
      await linkRingsApi.create(ringForm)
      ElMessage.success('已创建')
    }
    showRingDialog.value = false; loadRings()
  } catch (e: any) { ElMessage.error(e.response?.data?.detail || '保存失败') }
}

async function deleteRing(id: string) {
  try { await linkRingsApi.delete(id); ElMessage.success('已删除'); loadRings() }
  catch (e: any) { ElMessage.error('删除失败') }
}

// --- Target CRUD ---
async function manageTargets(ring: LinkRingRecord) {
  targetRing.value = ring
  try {
    targets.value = await linkRingsApi.listTargets(ring.id)
  } catch (e: any) {
    console.error('Failed to load targets', e)
    targets.value = []
  }
  showTargetDialog.value = true
}

function openTargetDialog(row?: any) {
  if (row) {
    editingTarget.value = true; editTargetId.value = row.id
    Object.assign(targetForm, {
      source_site_id:row.source_site_id||'', source_novel_id:row.source_novel_id||'',
      target_site_id:row.target_site_id||'', target_novel_id:row.target_novel_id||'',
      target_url:row.target_url||'', anchor_text:row.anchor_text||'{title}',
      sort_order:row.sort_order||0, is_active:row.is_active??true,
    })
  } else {
    editingTarget.value = false; editTargetId.value = ''
    Object.assign(targetForm, {source_site_id:'',source_novel_id:'',target_site_id:'',target_novel_id:'',target_url:'',anchor_text:'{title}',sort_order:0,is_active:true})
  }
  showSingleTarget.value = true
}

async function saveTarget() {
  const rid = targetRing.value?.id
  if (!rid) return
  try {
    if (editingTarget.value) {
      await linkRingsApi.updateTarget(rid, editTargetId.value, targetForm)
      ElMessage.success('已更新')
    } else {
      await linkRingsApi.createTarget(rid, targetForm)
      ElMessage.success('已添加')
    }
    showSingleTarget.value = false
    targets.value = await linkRingsApi.listTargets(rid)
  } catch (e: any) { ElMessage.error(e.response?.data?.detail || '保存失败') }
}

async function deleteTarget(id: string) {
  const rid = targetRing.value?.id
  if (!rid) return
  try {
    await linkRingsApi.deleteTarget(rid, id)
    ElMessage.success('已删除')
    targets.value = await linkRingsApi.listTargets(rid)
  } catch (e: any) { ElMessage.error('删除失败') }
}

onMounted(() => { loadRings(); loadSites() })
</script>
