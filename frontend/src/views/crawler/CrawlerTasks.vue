<template>
  <div>
    <div class="page-header">
      <h2>🕷️ 爬取任务</h2>
      <p>规则管理 · 直接/搜索采集 · 页面批量采集 · 任务监控</p>
    </div>

    <!-- Anti-Detect -->
    <div class="content-card" style="margin-bottom:16px;padding:10px 16px;display:flex;gap:20px;align-items:center;font-size:13px">
      <span style="font-weight:bold">🛡️ 反反采集</span>
      <el-tag size="small" type="success">UA轮换(15)</el-tag>
      <el-tag size="small" type="success">随机延迟</el-tag>
      <el-tag size="small" type="success">指数退避</el-tag>
    </div>

    <!-- ============ Rules ============ -->
    <div class="content-card" style="margin-bottom:16px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
        <h3 style="margin:0;font-size:15px">📋 采集规则</h3>
        <el-button size="small" type="primary" @click="openRuleDialog()">+ 添加</el-button>
      </div>
      <el-table :data="ruleList" stripe size="small">
        <el-table-column prop="source_name" label="规则名" width="90"/>
        <el-table-column prop="description" label="描述" min-width="180"/>
        <el-table-column prop="base_url" label="站点URL" width="220"/>
        <el-table-column label="操作" width="200">
          <template #default="{row}">
            <el-button link size="small" type="primary" @click="openRuleDialog(row.source_name)">编辑</el-button>
            <el-button link size="small" type="warning" @click="$router.push('/rules')">测试</el-button>
            <el-popconfirm title="删除?" @confirm="deleteRule(row.source_name)">
              <template #reference><el-button link size="small" type="danger">删除</el-button></template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </div>
    <!-- Rule Dialog -->
    <el-dialog v-model="showRuleDialog" :title="ruleEditing?'编辑规则':'添加规则'" width="650px" destroy-on-close>
      <el-form :model="ruleForm" label-width="80px">
        <el-form-item label="规则名"><el-input v-model="ruleForm.source_name" :disabled="!!ruleEditing"/></el-form-item>
        <el-form-item label="描述"><el-input v-model="ruleForm.description"/></el-form-item>
        <el-form-item label="站点URL"><el-input v-model="ruleForm.base_url"/></el-form-item>
        <el-form-item label="JSON"><el-input v-model="ruleForm.jsonText" type="textarea" :rows="14" style="font-family:monospace;font-size:12px"/></el-form-item>
      </el-form>
      <template #footer><el-button @click="showRuleDialog=false">取消</el-button><el-button type="primary" :loading="ruleSaving" @click="saveRule">保存</el-button></template>
    </el-dialog>

    <!-- ============ Crawl Panel ============ -->
    <div class="content-card" style="margin-bottom:16px">
      <h3 style="margin:0 0 12px 0;font-size:15px">🚀 采集面板</h3>
      <el-tabs v-model="crawlMode">

        <!-- SINGLE ------------------------------------------------------ -->
        <el-tab-pane label="📖 单本采集" name="single">
          <div style="margin-bottom:12px">
            <el-radio-group v-model="singleCrawlType" size="small">
              <el-radio-button value="direct">📌 直接采集</el-radio-button>
              <el-radio-button value="search">🔍 搜索匹配</el-radio-button>
            </el-radio-group>
          </div>
          <div style="display:flex;gap:12px;align-items:flex-end;flex-wrap:wrap">
            <div><div style="font-size:12px;color:#909399;margin-bottom:4px">小说</div><el-select v-model="singleNovelId" placeholder="选择小说" filterable style="width:280px"><el-option v-for="n in novels" :key="n.id" :label="`${n.title} (${n.author})`" :value="n.id"/></el-select></div>
            <div><div style="font-size:12px;color:#909399;margin-bottom:4px">规则</div><el-select v-model="singleSource" placeholder="规则" style="width:120px"><el-option v-for="r in ruleList" :key="r.source_name" :label="r.source_name" :value="r.source_name"/></el-select></div>
            <el-button v-if="singleCrawlType==='search'" size="small" :loading="previewLoading" :disabled="!singleNovelId||!singleSource" @click="doSearchPreview">🔍 搜索预览</el-button>
            <el-button type="primary" :loading="singleLoading" :disabled="!singleNovelId||!singleSource" @click="triggerSingle">{{ singleCrawlType==='search'?'搜索并采集':'开始采集' }}</el-button>
          </div>
          <div v-if="previewResult" style="margin-top:12px;padding:12px;background:#f0f9eb;border-radius:6px;font-size:13px">
            <div v-if="previewResult.best_match" style="color:#67c23a;font-weight:bold;margin-bottom:6px">✅ 最佳匹配: {{ previewResult.best_match.title }} — {{ previewResult.best_match.author }} ({{ previewResult.best_match._score }})</div>
            <div v-else style="color:#e6a23c;font-weight:bold;margin-bottom:6px">⚠️ 未找到高置信度匹配</div>
            <div style="max-height:200px;overflow-y:auto;margin-top:8px">
              <div v-for="(c,idx) in previewResult.candidates.slice(0,10)" :key="idx" style="padding:4px 8px;margin-bottom:4px;background:#fff;border-radius:4px;display:flex;justify-content:space-between">
                <span>{{ c.title }} — {{ c.author||'未知' }}</span>
                <el-tag size="small" :type="c._score>=30?'success':'info'">评分 {{ c._score }}</el-tag>
              </div>
            </div>
          </div>
        </el-tab-pane>

        <!-- BATCH ------------------------------------------------------- -->
        <el-tab-pane label="📚 批量采集" name="batch">
          <div style="margin-bottom:12px">
            <el-radio-group v-model="batchCrawlType" size="small">
              <el-radio-button value="direct">📌 直接采集</el-radio-button>
              <el-radio-button value="search">🔍 搜索匹配</el-radio-button>
            </el-radio-group>
          </div>
          <div style="margin-bottom:12px"><div style="font-size:12px;color:#909399;margin-bottom:4px">小说（已选 {{ batchNovelIds.length }} 本）</div><el-select v-model="batchNovelIds" placeholder="搜索多选" filterable multiple collapse-tags collapse-tags-tooltip style="width:100%"><el-option v-for="n in novels" :key="n.id" :label="`${n.title} (${n.author})`" :value="n.id"/></el-select></div>
          <div style="display:flex;gap:12px;align-items:flex-end">
            <div><div style="font-size:12px;color:#909399;margin-bottom:4px">规则</div><el-select v-model="batchSource" placeholder="规则" style="width:120px"><el-option v-for="r in ruleList" :key="r.source_name" :label="r.source_name" :value="r.source_name"/></el-select></div>
            <el-button type="primary" :loading="batchLoading" :disabled="!batchNovelIds.length||!batchSource" @click="triggerBatch">批量采集 ({{ batchNovelIds.length }})</el-button>
            <el-button @click="batchNovelIds=[]">清空</el-button>
          </div>
        </el-tab-pane>

        <!-- PAGE -------------------------------------------------------- -->
        <el-tab-pane label="📄 页面采集" name="page">
          <div style="font-size:13px;color:#909399;margin-bottom:8px">提取 → 测试目录/章节 → 通过后导入采集</div>
          <div style="display:flex;gap:8px;align-items:flex-end;flex-wrap:wrap;margin-bottom:12px">
            <div style="flex:1;min-width:260px">
              <div style="font-size:12px;color:#909399;margin-bottom:4px">页面 URL</div>
              <el-input v-model="pageUrl" placeholder="https://www.23qb.net/book/postdate_0_0_0_0_0_0_0_1_0.html" clearable @keyup.enter="doPagePreview"/>
            </div>
            <div><div style="font-size:12px;color:#909399;margin-bottom:4px">起始页</div><el-input-number v-model="pageFrom" :min="1" size="small" style="width:65px"/></div>
            <div><div style="font-size:12px;color:#909399;margin-bottom:4px">结束页</div><el-input-number v-model="pageTo" :min="1" size="small" style="width:65px"/></div>
            <div><div style="font-size:12px;color:#909399;margin-bottom:4px">规则</div><el-select v-model="pageSource" placeholder="规则" style="width:100px"><el-option v-for="r in ruleList" :key="r.source_name" :label="r.source_name" :value="r.source_name"/></el-select></div>
            <el-button type="warning" :loading="pagePreviewLoading" :disabled="!pageUrl" @click="doPagePreview">🔍 提取</el-button>
            <el-button type="info" :loading="pageTestLoading" :disabled="!pagePreview||pagePreview.novels.length===0" @click="doPageTest()">🧪 测试全部</el-button>
            <el-button size="small" :loading="pageTestLoading" :disabled="pageSelectedIds.length===0" @click="doPageTest(pageSelectedIds)">🧪 测试选中 ({{ pageSelectedIds.length }})</el-button>
          </div>
          <!-- Results with test status -->
          <div v-if="pagePreview" style="margin-bottom:12px">
            <div style="font-size:13px;margin-bottom:8px;font-weight:bold" :style="{color: pageTestDone ? (pagePassedCount===pagePreview.novel_count?'#67c23a':'#e6a23c') : '#409eff'}">
              {{ pageTestDone ? (pagePassedCount===pagePreview.novel_count ? '✅' : '⚠️') : '📋' }}
              {{ pagePreview.novel_count }} 本小说
              <span v-if="pageTestDone"> | 🧪 通过 {{ pagePassedCount }} / 失败 {{ pagePreview.novel_count - pagePassedCount }}</span>
              <span v-else> | 点击「🧪 测试全部」验证目录和章节提取</span>
            </div>
            <div v-if="pagePreview.novels.length > 0" style="max-height:360px;overflow-y:auto;border:1px solid #ebeef5;border-radius:4px">
              <el-table :data="pagePreview.novels" size="small" @selection-change="onPageSelectionChange" max-height="340">
                <el-table-column type="selection" width="36" :selectable="(row:any)=>row._test?.passed"/>
                <el-table-column prop="title" label="小说名称" min-width="180">
                  <template #default="{row}">
                    <span>{{ row.title }}</span>
                    <el-tag v-if="row._testing" size="small" type="warning" style="margin-left:6px">测试中</el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="book_id" label="Book ID" width="80"/>
                <el-table-column label="目录" width="80">
                  <template #default="{row}">
                    <span v-if="row._test?.catalog_ok" style="color:#67c23a">✅ {{ row._test?.chapter_count }}章</span>
                    <span v-else-if="row._test && !row._test.catalog_ok" style="color:#f56c6c">❌</span>
                    <span v-else style="color:#c0c4cc">-</span>
                  </template>
                </el-table-column>
                <el-table-column label="章节" width="80">
                  <template #default="{row}">
                    <span v-if="row._test?.chapter_ok" style="color:#67c23a">✅ {{ row._test?.content_len }}</span>
                    <span v-else-if="row._test && !row._test.chapter_ok" style="color:#f56c6c">❌</span>
                    <span v-else style="color:#c0c4cc">-</span>
                  </template>
                </el-table-column>
                <el-table-column label="信息" min-width="160">
                  <template #default="{row}">
                    <span v-if="row._test?.chapter_ok" style="font-size:11px;color:#909399">{{ row._test?.chapter_title }}</span>
                    <span v-else-if="row._test?.error" style="font-size:11px;color:#f56c6c">{{ row._test?.error }}</span>
                    <span v-else style="color:#c0c4cc">等待测试</span>
                  </template>
                </el-table-column>
                <el-table-column label="URL" width="60">
                  <template #default="{row}"><el-link :href="row.url" target="_blank" size="small">打开</el-link></template>
                </el-table-column>
                <el-table-column label="测试" width="60">
                  <template #default="{row}">
                    <el-button size="small" :loading="row._testing" :type="row._test?.passed?'success':(row._test?'danger':'info')" @click="doPageTest([row.book_id])" :disabled="row._testing">🧪</el-button>
                  </template>
                </el-table-column>
              </el-table>
            </div>
            <div style="margin-top:8px;display:flex;gap:8px">
              <el-button size="small" @click="toggleSelectAll">全选通过 / 取消</el-button>
              <el-button size="small" type="primary" :loading="pageTriggerLoading" :disabled="pageSelectedIds.length===0" @click="triggerPageCrawl">
                导入选中 ({{ pageSelectedIds.length }}) 并采集
              </el-button>
              <el-button size="small" type="success" :loading="pageTriggerLoading" :disabled="!pageTestDone||pagePassedCount===0" @click="triggerPageCrawlAll">
                导入全部通过 ({{ pagePassedCount }})
              </el-button>
            </div>
          </div>
          <div v-if="pageError" style="color:#f56c6c;font-size:13px">❌ {{ pageError }}</div>
        </el-tab-pane>

      </el-tabs>
    </div>

    <!-- ============ Live Progress ============ -->
    <LiveProgress
      v-if="activeStreamTaskId"
      :task-id="activeStreamTaskId"
      :base-url="baseUrl"
      @done="activeStreamTaskId = ''"
    />

    <!-- ============ Task List ============ -->
    <div class="content-card">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
        <h3 style="margin:0;font-size:15px">📊 任务列表</h3>
        <div style="display:flex;gap:8px;align-items:center">
          <el-select v-model="filterStatus" placeholder="状态" clearable @change="loadTasks" style="width:110px" size="small">
            <el-option label="等待中" value="pending"/><el-option label="运行中" value="running"/>
            <el-option label="已完成" value="completed"/><el-option label="失败" value="failed"/>
          </el-select>
          <el-button size="small" :icon="RefreshRight" @click="loadTasks">刷新</el-button>
          <el-checkbox v-model="autoRefresh" size="small">自动</el-checkbox>
          <el-popconfirm title="删除选中任务?" @confirm="batchDeleteTasks">
            <template #reference>
              <el-button size="small" type="danger" :disabled="taskSelectedIds.length===0">批量删除 ({{ taskSelectedIds.length }})</el-button>
            </template>
          </el-popconfirm>
        </div>
      </div>
      <el-table :data="tasks" stripe v-loading="loading" @selection-change="onTaskSelectionChange">
        <el-table-column type="selection" width="36" :selectable="(row:any)=>row.status!=='running'"/>
        <el-table-column label="小说" min-width="140"><template #default="{row}"><span style="font-size:12px">{{ novelMap[row.novel_id]||row.novel_id?.slice(0,8)+'...' }}</span></template></el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{row}">
            <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
            <el-progress v-if="row.status==='running'" :percentage="100" :indeterminate="true" :stroke-width="4" style="margin-top:4px;width:60px"/>
          </template>
        </el-table-column>
        <el-table-column prop="chapters_found" label="发现" width="60"/><el-table-column prop="chapters_added" label="新增" width="60"/>
        <el-table-column label="耗时" width="80"><template #default="{row}">{{ elapsed(row) }}</template></el-table-column>
        <el-table-column label="开始" width="140"><template #default="{row}">{{ fmt(row.started_at) }}</template></el-table-column>
        <el-table-column label="信息" min-width="160">
          <template #default="{row}">
            <div v-if="editingTaskId===row.id" style="display:flex;gap:4px">
              <el-input v-model="editMsg" size="small" style="width:140px"/>
              <el-button size="small" type="primary" @click="saveTaskEdit(row.id)">保存</el-button>
              <el-button size="small" @click="editingTaskId=''">取消</el-button>
            </div>
            <span v-else-if="row.error_message" :style="{color:row.status==='completed'?'#67c23a':'#f56c6c',fontSize:'12px',cursor:'pointer'}" @dblclick="startEdit(row)">{{ row.error_message }}</span>
            <span v-else style="color:#c0c4cc;font-size:12px">- (双击编辑)</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="240">
          <template #default="{row}">
            <el-button v-if="row.status==='pending'" link size="small" type="success" @click="startTask(row.id)">开始</el-button>
            <el-button v-if="row.status==='running'" link size="small" type="warning" @click="stopTask(row.id)">停止</el-button>
            <el-button v-if="row.status==='failed'||row.status==='completed'" link size="small" type="primary" @click="retryTask(row.id)">重试</el-button>
            <el-button link size="small" type="info" @click="startEdit(row)">编辑</el-button>
            <el-popconfirm title="删除?" @confirm="deleteTask(row.id)">
              <template #reference><el-button link size="small" type="danger" :disabled="row.status==='running'">删除</el-button></template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
      <div style="margin-top:12px;display:flex;justify-content:flex-end">
        <el-pagination v-model:current-page="pagination.page" v-model:page-size="pagination.size" :total="pagination.total" :page-sizes="[10,20,50]" layout="total,sizes,prev,pager,next" @change="loadTasks"/>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref,reactive,computed,onMounted,onUnmounted,watch } from 'vue'
import { ElMessage } from 'element-plus'
import { RefreshRight } from '@element-plus/icons-vue'
import LiveProgress from '@/components/crawler/LiveProgress.vue'
import { crawlerApi, type SearchPreviewResult, type PagePreviewResult } from '@/api/crawler'
import { novelsApi, type NovelRecord } from '@/api/novels'

const baseUrl = window.location.origin
const activeStreamTaskId = ref('')

// ---- Rules ----
const ruleList=ref<any[]>([]),showRuleDialog=ref(false),ruleEditing=ref<string|null>(null),ruleSaving=ref(false)
const ruleForm=reactive({source_name:'',description:'',base_url:'',jsonText:''})
async function loadRules(){try{ruleList.value=await crawlerApi.listRules()}catch{}}
function openRuleDialog(name?:string){if(name){ruleEditing.value=name;crawlerApi.getRule(name).then(d=>{ruleForm.source_name=d.source_name||name;ruleForm.description=d.description||'';ruleForm.base_url=d.base_url||'';ruleForm.jsonText=JSON.stringify(d,null,2);showRuleDialog.value=true}).catch(()=>ElMessage.error('加载失败'))}else{ruleEditing.value=null;ruleForm.source_name='';ruleForm.description='';ruleForm.base_url='';ruleForm.jsonText='';showRuleDialog.value=true}}
async function saveRule(){ruleSaving.value=true;try{const d=JSON.parse(ruleForm.jsonText);d.source_name=ruleForm.source_name;d.description=ruleForm.description||d.description;d.base_url=ruleForm.base_url||d.base_url;await crawlerApi.saveRule(ruleForm.source_name,d);ElMessage.success('已保存');showRuleDialog.value=false;ruleEditing.value=null;loadRules()}catch(e:any){ElMessage.error(e.response?.data?.detail||'保存失败')}finally{ruleSaving.value=false}}
async function deleteRule(name:string){try{await crawlerApi.deleteRule(name);ElMessage.success('已删除');loadRules()}catch(e:any){ElMessage.error(e.response?.data?.detail||'失败')}}

// ---- Novels ----
const novels=ref<NovelRecord[]>([])
const novelMap=computed(()=>{const m:Record<string,string>={};novels.value.forEach(n=>m[n.id]=`${n.title} (${n.author})`);return m})

// ---- Single ----
const crawlMode=ref('single'),singleNovelId=ref(''),singleSource=ref(''),singleLoading=ref(false),singleCrawlType=ref<'direct'|'search'>('direct')
async function triggerSingle(){if(!singleNovelId.value||!singleSource.value)return;singleLoading.value=true;try{const t=await crawlerApi.trigger(singleNovelId.value,singleSource.value,singleCrawlType.value);activeStreamTaskId.value=t.id;ElMessage.success('已提交');loadTasks()}catch(e:any){ElMessage.error(e.response?.data?.detail||'失败')}finally{singleLoading.value=false}}
const previewLoading=ref(false),previewResult=ref<SearchPreviewResult|null>(null)
async function doSearchPreview(){if(!singleNovelId.value||!singleSource.value)return;previewLoading.value=true;previewResult.value=null;try{previewResult.value=await crawlerApi.searchPreview(singleNovelId.value,singleSource.value)}catch(e:any){ElMessage.error(e.response?.data?.detail||'搜索预览失败')}finally{previewLoading.value=false}}

// ---- Batch ----
const batchNovelIds=ref<string[]>([]),batchSource=ref(''),batchLoading=ref(false),batchCrawlType=ref<'direct'|'search'>('direct')
async function triggerBatch(){if(!batchNovelIds.value.length||!batchSource.value)return;batchLoading.value=true;try{const r=await crawlerApi.triggerBatch(batchNovelIds.value,batchSource.value,batchCrawlType.value);ElMessage.success(r.message);batchNovelIds.value=[];loadTasks()}catch(e:any){ElMessage.error(e.response?.data?.detail||'失败')}finally{batchLoading.value=false}}

// ---- Page ----
const pageUrl=ref(''),pageSource=ref(''),pageFrom=ref(1),pageTo=ref(1),pagePreviewLoading=ref(false),pageTestLoading=ref(false),pageTriggerLoading=ref(false),pagePreview=ref<PagePreviewResult|null>(null),pageError=ref(''),pageSelectedIds=ref<string[]>([]),pageTestDone=ref(false),pagePassedCount=ref(0)
const pageSelection=ref<any[]>([])
function onPageSelectionChange(rows:any[]){pageSelection.value=rows;pageSelectedIds.value=rows.map((r:any)=>r.book_id)}
function toggleSelectAll(){if(!pagePreview.value)return;const passed=pagePreview.value.novels.filter((n:any)=>n._test?.passed);if(pageSelectedIds.value.length===passed.length){pageSelectedIds.value=[]}else{pageSelectedIds.value=passed.map((n:any)=>n.book_id)}}
async function doPagePreview(){if(!pageUrl.value)return;pagePreviewLoading.value=true;pagePreview.value=null;pageError.value='';pageTestDone.value=false;pagePassedCount.value=0;try{pagePreview.value=await crawlerApi.pagePreview(pageUrl.value,pageSource.value||undefined,pageFrom.value,pageTo.value);pageSelectedIds.value=[]}catch(e:any){pageError.value=e.response?.data?.detail||'提取失败'}finally{pagePreviewLoading.value=false}}
async function doPageTest(ids?:string[]){if(!pageUrl.value||!pagePreview.value)return;pageTestLoading.value=true;pageError.value='';const isPartial=ids&&ids.length>0;if(!isPartial)pageTestDone.value=false;try{const r=await crawlerApi.pageTest(pageUrl.value,pageSource.value||undefined,pageFrom.value,pageTo.value,ids);if(isPartial){const novelMap=new Map(pagePreview.value.novels.map((n:any)=>[n.book_id,n]));for(const n of r.novels){const existing=novelMap.get(n.book_id);if(existing)Object.assign(existing,{_test:n._test,_testing:false})}pagePassedCount.value=pagePreview.value.novels.filter((n:any)=>n._test?.passed).length;pageTestDone.value=pagePreview.value.novels.every((n:any)=>n._test!==null&&n._test!==undefined)}else{pagePreview.value.novels=r.novels;pagePassedCount.value=r.passed;pageTestDone.value=true}if(r.failed>0)ElMessage.warning(`${r.passed}/${r.total} 通过，${r.failed} 失败`);else ElMessage.success(`${r.total} 本全部通过!`)}catch(e:any){pageError.value=e.response?.data?.detail||'测试失败'}finally{pageTestLoading.value=false}}
async function triggerPageCrawl(){if(!pageSelectedIds.value.length||!pageUrl.value||!pageSource.value)return;pageTriggerLoading.value=true;try{const r=await crawlerApi.triggerPage(pageUrl.value,pageSource.value,pageSelectedIds.value,pageFrom.value,pageTo.value);ElMessage.success(r.message);pagePreview.value=null;loadTasks()}catch(e:any){ElMessage.error(e.response?.data?.detail||'失败')}finally{pageTriggerLoading.value=false}}
async function triggerPageCrawlAll(){if(!pageUrl.value||!pageSource.value)return;pageTriggerLoading.value=true;const passedIds=pagePreview.value?.novels.filter((n:any)=>n._test?.passed).map((n:any)=>n.book_id)||[];try{const r=await crawlerApi.triggerPage(pageUrl.value,pageSource.value,passedIds,pageFrom.value,pageTo.value);ElMessage.success(r.message);pagePreview.value=null;loadTasks()}catch(e:any){ElMessage.error(e.response?.data?.detail||'失败')}finally{pageTriggerLoading.value=false}}

// ---- Tasks ----
const loading=ref(false),tasks=ref<any[]>([]),filterStatus=ref(''),autoRefresh=ref(true);let timer:any=null
const pagination=reactive({page:1,size:20,total:0})
const editingTaskId=ref(''),editMsg=ref(''),taskSelectedIds=ref<string[]>([])
function statusType(s:string){const m:Record<string,string>={pending:'info',running:'warning',completed:'success',failed:'danger'};return m[s]||'info'}
function statusLabel(s:string){const m:Record<string,string>={pending:'等待中',running:'运行中',completed:'已完成',failed:'失败'};return m[s]||s}
function fmt(d:string|null){return d?new Date(d).toLocaleString('zh-CN'):'-'}
function elapsed(row:any){if(!row.started_at)return'-';const end=row.finished_at?new Date(row.finished_at):new Date();const s=(end.getTime()-new Date(row.started_at).getTime())/1000;if(s<60)return`${Math.round(s)}秒`;return`${Math.floor(s/60)}分${Math.round(s%60)}秒`}
function onTaskSelectionChange(rows:any[]){taskSelectedIds.value=rows.map((r:any)=>r.id)}
function startEdit(row:any){editingTaskId.value=row.id;editMsg.value=row.error_message||''}
async function saveTaskEdit(id:string){try{await crawlerApi.updateTask(id,{error_message:editMsg.value});ElMessage.success('已更新');editingTaskId.value='';loadTasks()}catch(e:any){ElMessage.error('更新失败')}}
async function startTask(id:string){try{await crawlerApi.startTask(id);ElMessage.success('任务已开始');loadTasks()}catch(e:any){ElMessage.error(e.response?.data?.detail||'启动失败')}}
async function stopTask(id:string){try{await crawlerApi.stopTask(id);ElMessage.success('任务已停止');loadTasks()}catch(e:any){ElMessage.error(e.response?.data?.detail||'停止失败')}}
async function retryTask(id:string){try{await crawlerApi.retryTask(id);ElMessage.success('已提交重试');loadTasks()}catch(e:any){ElMessage.error(e.response?.data?.detail||'重试失败')}}
async function loadTasks(){loading.value=true;try{const r=await crawlerApi.listTasks({status:filterStatus.value||undefined,page:pagination.page,size:pagination.size});tasks.value=r.items;pagination.total=r.total}catch{}finally{loading.value=false}}
async function deleteTask(id:string){try{await crawlerApi.deleteTask(id);ElMessage.success('已删除');loadTasks()}catch(e:any){ElMessage.error(e.response?.data?.detail||'失败')}}
async function batchDeleteTasks(){if(!taskSelectedIds.value.length)return;try{const r=await crawlerApi.batchDeleteTasks(taskSelectedIds.value);ElMessage.success(`删除 ${r.deleted} 个，跳过 ${r.skipped} 个运行中`);taskSelectedIds.value=[];loadTasks()}catch(e:any){ElMessage.error('批量删除失败')}}
watch(autoRefresh,(on)=>{if(on)timer=setInterval(loadTasks,5000);else{clearInterval(timer);timer=null}})

onMounted(async()=>{await loadRules();try{const r=await novelsApi.list({size:200});novels.value=r.items}catch{};loadTasks();if(autoRefresh.value)timer=setInterval(loadTasks,5000)})
onUnmounted(()=>{if(timer)clearInterval(timer)})
</script>
