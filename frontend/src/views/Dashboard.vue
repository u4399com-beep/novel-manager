<template>
  <div>
    <div class="page-header">
      <h2>📊 仪表盘</h2>
      <p>系统概览 · 采集进度 · 资源占用</p>
    </div>

    <!-- Stats Cards -->
    <div class="stats-row">
      <div class="stat-card">
        <div class="stat-icon" style="background:linear-gradient(135deg,#667eea,#764ba2)"><el-icon size="24"><Reading/></el-icon></div>
        <div><div class="stat-value">{{ stats.novels?.toLocaleString() || 0 }}</div><div class="stat-label">小说总数</div></div>
      </div>
      <div class="stat-card">
        <div class="stat-icon" style="background:linear-gradient(135deg,#f093fb,#f5576c)"><el-icon size="24"><Document/></el-icon></div>
        <div><div class="stat-value">{{ stats.chapters?.toLocaleString() || 0 }}</div><div class="stat-label">章节总数</div></div>
      </div>
      <div class="stat-card">
        <div class="stat-icon" style="background:linear-gradient(135deg,#4facfe,#00f2fe)"><el-icon size="24"><Edit/></el-icon></div>
        <div><div class="stat-value">{{ fmtWords(stats.words) }}</div><div class="stat-label">总字数</div></div>
      </div>
      <div class="stat-card">
        <div class="stat-icon" style="background:linear-gradient(135deg,#43e97b,#38f9d7)"><el-icon size="24"><Download/></el-icon></div>
        <div><div class="stat-value">{{ stats.content_files?.toLocaleString() || 0 }}</div><div class="stat-label">内容文件</div></div>
      </div>
    </div>

    <!-- Task Progress -->
    <div class="content-card" style="margin-bottom:16px">
      <h3 style="margin:0 0 12px 0;font-size:15px">📈 采集进度</h3>
      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:12px;text-align:center">
        <div><div style="font-size:24px;font-weight:700;color:#409eff">{{ stats.tasks?.total || 0 }}</div><div style="font-size:12px;color:#999">全部任务</div></div>
        <div><div style="font-size:24px;font-weight:700;color:#e6a23c">{{ stats.tasks?.pending || 0 }}</div><div style="font-size:12px;color:#999">待处理</div></div>
        <div><div style="font-size:24px;font-weight:700;color:#67c23a">{{ stats.tasks?.completed || 0 }}</div><div style="font-size:12px;color:#999">已完成</div></div>
        <div><div style="font-size:24px;font-weight:700;color:#f56c6c">{{ stats.tasks?.failed || 0 }}</div><div style="font-size:12px;color:#999">失败</div></div>
      </div>
      <el-progress :percentage="stats.progress || 0" :stroke-width="16" :text-inside="true" :status="stats.progress>=100?'success':''"/>
      <div style="text-align:center;margin-top:6px;font-size:12px;color:#999">
        队列: {{ wd.runner_alive ? '🟢 运行中' : '🔴 已停止' }}
        看门狗: {{ wd.watchdog_alive ? '🟢' : '🔴' }}
        <span v-if="wd.queue?.stuck > 0" style="color:#e6a23c">⚠ {{ wd.queue.stuck }} 卡死</span>
      </div>
      <div style="text-align:center;margin-top:8px;display:flex;gap:8px;justify-content:center">
        <el-button size="small" @click="refreshWd">🔄 刷新</el-button>
        <el-button size="small" type="warning" @click="restartQueue" :loading="restarting">🔁 重启队列</el-button>
        <el-button size="small" type="danger" @click="restartWatchdog" :loading="restartingWd">🛡 重启看门狗</el-button>
      </div>
    </div>

    <!-- Repair Tools -->
    <div class="content-card" style="margin-bottom:16px">
      <h3 style="margin:0 0 12px 0;font-size:15px">🔧 修复工具</h3>
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px">
        <!-- Empty Chapters -->
        <div style="padding:12px;background:#fafbfc;border-radius:8px">
          <div style="font-weight:600;margin-bottom:4px">📝 空章节</div>
          <div style="font-size:24px;font-weight:700;color:#e6a23c">{{ rp.empty_chapters != null ? rp.empty_chapters.toLocaleString() : '—' }}</div>
          <div style="margin-top:8px;display:flex;gap:6px">
            <el-button size="small" @click="countRepair('chapters')" :loading="counting.chapters">📊 统计</el-button>
            <el-button v-if="!rp.tasks_running?.repair_chapters" size="small" type="primary" @click="startRepair('chapters')">▶ 修复</el-button>
            <el-button v-else size="small" type="danger" @click="stopRepair('chapters')">⏹ 停止</el-button>
          </div>
        </div>
        <!-- No Cover -->
        <div style="padding:12px;background:#fafbfc;border-radius:8px">
          <div style="font-weight:600;margin-bottom:4px">🖼 无封面</div>
          <div style="font-size:24px;font-weight:700;color:#e6a23c">{{ rp.no_cover != null ? rp.no_cover.toLocaleString() : '—' }}</div>
          <div style="margin-top:8px;display:flex;gap:6px">
            <el-button size="small" @click="countRepair('covers')" :loading="counting.covers">📊 统计</el-button>
            <el-button v-if="!rp.tasks_running?.repair_covers" size="small" type="primary" @click="startRepair('covers')">▶ 修复</el-button>
            <el-button v-else size="small" type="danger" @click="stopRepair('covers')">⏹ 停止</el-button>
          </div>
        </div>
        <!-- Missing Info -->
        <div style="padding:12px;background:#fafbfc;border-radius:8px">
          <div style="font-weight:600;margin-bottom:4px">📋 信息不全</div>
          <div style="font-size:14px;color:#909399">
            缺简介: {{ rp.no_description != null ? rp.no_description.toLocaleString() : '—' }}<br/>
            缺作者: {{ rp.no_author != null ? rp.no_author.toLocaleString() : '—' }}
          </div>
          <div style="margin-top:8px;display:flex;gap:6px">
            <el-button size="small" @click="countRepair('info')" :loading="counting.info">📊 统计</el-button>
            <el-button v-if="!rp.tasks_running?.repair_info" size="small" type="primary" @click="startRepair('info')">▶ 修复</el-button>
            <el-button v-else size="small" type="danger" @click="stopRepair('info')">⏹ 停止</el-button>
          </div>
        </div>
      </div>
    </div>

    <!-- System Resources -->
    <div class="content-card" style="margin-bottom:16px">
      <h3 style="margin:0 0 12px 0;font-size:15px">💻 系统占用</h3>
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:16px">
        <div>
          <div style="font-size:12px;color:#999;margin-bottom:4px">内容文件</div>
          <div style="font-size:18px;font-weight:700">{{ stats.content_files?.toLocaleString() || 0 }} 个</div>
          <div style="font-size:12px;color:#999">~{{ stats.content_size_mb || 0 }} MB</div>
        </div>
        <div>
          <div style="font-size:12px;color:#999;margin-bottom:4px">数据库</div>
          <div style="font-size:18px;font-weight:700">{{ stats.novels?.toLocaleString() || 0 }} 本</div>
          <div style="font-size:12px;color:#999">{{ stats.tasks?.total || 0 }} 任务</div>
        </div>
        <div>
          <div style="font-size:12px;color:#999;margin-bottom:4px">估算总量</div>
          <div style="font-size:18px;font-weight:700">~{{ estTotal }} MB</div>
          <div style="font-size:12px;color:#999">{{ stats.progress || 0 }}% 完成</div>
        </div>
      </div>
    </div>

    <!-- Refresh -->
    <div style="text-align:center;color:#999;font-size:12px">
      自动刷新每10秒 · 上次: {{ lastRefresh }}
      <el-button size="small" text @click="loadStats">🔄 立即刷新</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { Reading, Document, Edit, Download } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import request from '@/utils/request'

const wd = reactive<any>({ queue: {}, runner_alive: false, watchdog_alive: false, empty_chapters: 0 })
const rp = reactive<any>({ tasks_running: {}, empty_chapters: null, no_cover: null, no_description: null, no_author: null })
const counting = reactive({ chapters: false, covers: false, info: false })
const restarting = ref(false)
const restartingWd = ref(false)

async function countRepair(task: string) {
  const key = task === 'chapters' ? 'chapters' : task === 'covers' ? 'covers' : 'info'
  counting[key] = true
  try {
    const r = await request.get('/repair/status')
    const d = r.data
    if (task === 'chapters') rp.empty_chapters = d.empty_chapters
    if (task === 'covers') rp.no_cover = d.no_cover
    if (task === 'info') {
      rp.no_description = d.no_description
      rp.no_author = d.no_author
    }
    ElMessage.success('统计完成')
  } catch { ElMessage.error('统计失败') }
  counting[key] = false
}

async function loadRepair() {
  try { const r = await request.get('/repair/status'); Object.assign(rp, r.data) } catch {}
}

async function startRepair(task: string) {
  try {
    await request.post(`/repair/${task}`)
    ElMessage.success(`已启动: ${task}`)
    setTimeout(loadRepair, 2000)
  } catch (e: any) { ElMessage.error(e.response?.data?.message || '失败') }
}

async function stopRepair(task: string) {
  try {
    await request.post(`/repair/${task}/stop`)
    ElMessage.success(`已停止: ${task}`)
    setTimeout(loadRepair, 2000)
  } catch { ElMessage.error('失败') }
}

const stats = reactive<any>({ tasks: {}, progress: 0 })
const lastRefresh = ref('')
let timer: any = null

const estTotal = computed(() => {
  return Math.round(540 + (stats.progress || 0) / 100 * 1200)
})

function fmtWords(n: number) {
  if (!n) return '0'
  if (n >= 10000) return (n / 10000).toFixed(1) + '万'
  return n.toLocaleString()
}

async function loadStats() {
  try {
    const r = await request.get('/crawler/stats')
    Object.assign(stats, r.data)
    lastRefresh.value = new Date().toLocaleTimeString('zh-CN')
  } catch (e: any) {
    console.error('Failed to load stats', e)
  }
}

async function refreshWd() {
  try {
    const r = await request.get('/watchdog/status')
    Object.assign(wd, r.data)
  } catch {}
}

async function restartQueue() {
  restarting.value = true
  try {
    await request.post('/watchdog/restart')
    ElMessage.success('队列已重启')
    setTimeout(refreshWd, 2000)
  } catch { ElMessage.error('重启失败') }
  restarting.value = false
}

async function restartWatchdog() {
  restartingWd.value = true
  try {
    await request.post('/watchdog/restart-watchdog')
    ElMessage.success('看门狗已重启')
    setTimeout(refreshWd, 2000)
  } catch { ElMessage.error('重启失败') }
  restartingWd.value = false
}

onMounted(() => {
  loadStats()
  refreshWd()
  loadRepair()
  // Only watchdog/queue auto-refresh (not stats/repair)
  timer = setInterval(refreshWd, 10000)
})
onUnmounted(() => { if (timer) clearInterval(timer) })
</script>
