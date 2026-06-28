<template>
  <div class="live-progress" v-if="visible">
    <div class="content-card" style="margin-bottom:16px">
      <!-- Header -->
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
        <h3 style="margin:0;font-size:15px">📡 实时采集进度</h3>
        <div style="display:flex;gap:8px;align-items:center">
          <el-tag :type="statusTag" size="small">{{ statusText }}</el-tag>
          <el-button size="small" text @click="visible=false">✕ 关闭</el-button>
        </div>
      </div>

      <!-- Progress bar + stats -->
      <div style="margin-bottom:12px">
        <el-progress
          :percentage="percent"
          :status="progressStatus"
          :stroke-width="16"
          :text-inside="true"
        />
      </div>
      <div style="display:flex;gap:24px;font-size:13px;margin-bottom:12px">
        <span>📖 {{ current }} / {{ total }} 章</span>
        <span>⚡ {{ speed }} 章/秒</span>
        <span>⏱ 剩余 {{ eta }}</span>
      </div>

      <!-- Chapter log (scrollable) -->
      <div
        ref="logEl"
        style="max-height:260px;overflow-y:auto;background:#fafafa;border-radius:6px;padding:8px 12px;font-size:12px;font-family:monospace"
      >
        <div v-for="(line, i) in log" :key="i" style="margin-bottom:3px;line-height:1.5">
          <span style="color:#909399">{{ line.time }}</span>
          <span :style="{color:line.color,marginLeft:'8px'}">{{ line.msg }}</span>
        </div>
      </div>

      <!-- Current chapter content preview -->
      <div v-if="preview.title" style="margin-top:12px;padding:10px;background:#f0f9eb;border-radius:6px;font-size:13px">
        <div style="font-weight:bold;color:#303133;margin-bottom:4px">📄 {{ preview.title }}</div>
        <div style="color:#606266;line-height:1.6;max-height:120px;overflow-y:auto">
          {{ preview.text || '(空章节)' }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'

const props = defineProps<{ taskId: string; baseUrl: string }>()
const emit = defineEmits(['done'])

const visible = ref(true)
const current = ref(0)
const total = ref(0)
const speed = ref(0)
const eta = ref('--')
const statusText = ref('连接中...')
const statusTag = ref<'info'|'warning'|'success'|'danger'>('info')
const preview = ref({ title: '', text: '' })
const log = ref<Array<{ time: string; msg: string; color: string }>>([])
const logEl = ref<HTMLElement | null>(null)
let eventSource: EventSource | null = null

const percent = computed(() => (total.value > 0 ? Math.round((current.value / total.value) * 100) : 0))
const progressStatus = computed(() => {
  if (statusTag.value === 'success') return 'success'
  if (statusTag.value === 'danger') return 'exception'
  if (current.value > 0) return undefined
  return undefined
})

function addLog(msg: string, color = '#303133') {
  const now = new Date().toLocaleTimeString('zh-CN')
  log.value.push({ time: now, msg, color })
  if (log.value.length > 200) log.value.shift()
  nextTick(() => {
    if (logEl.value) logEl.value.scrollTop = logEl.value.scrollHeight
  })
}

function connect() {
  if (!props.taskId || !props.baseUrl) return
  const url = `${props.baseUrl}/api/v1/crawler/stream/${props.taskId}`

  eventSource = new EventSource(url)

  eventSource.onmessage = (e) => {
    try {
      const d = JSON.parse(e.data)
      switch (d.type) {
        case 'start':
          addLog(`开始采集: ${d.novel_title || ''}`, '#409eff')
          statusText.value = '运行中'
          statusTag.value = 'warning'
          break
        case 'status':
          addLog(d.message || d.status, '#409eff')
          if (d.status === 'completed') {
            statusText.value = '已完成'
            statusTag.value = 'success'
            addLog(`✅ ${d.message || '完成'} | ${d.total_chapters || 0}章 | ${d.total_time || 0}秒`, '#67c23a')
            emit('done')
          } else if (d.status === 'failed') {
            statusText.value = '失败'
            statusTag.value = 'danger'
          }
          break
        case 'progress':
          total.value = d.total || 0
          addLog(d.message || `准备采集 ${d.total} 章`, '#909399')
          break
        case 'chapter':
          current.value = d.index || 0
          total.value = d.total || total.value
          speed.value = d.speed || 0
          eta.value = d.eta ? `${d.eta}秒` : '--'
          addLog(d.message || `[${d.index}/${d.total}] ${d.title}`, '#303133')
          if (d.content_preview) {
            preview.value = { title: d.title || '', text: d.content_preview }
          }
          break
        case 'error':
          addLog(`❌ ${d.message}`, '#f56c6c')
          statusText.value = '失败'
          statusTag.value = 'danger'
          break
        case 'done':
          if (eventSource) { eventSource.close(); eventSource = null }
          break
        case 'heartbeat':
          break
      }
    } catch { /* parse error — non-JSON line */ }
  }

  eventSource.onerror = () => {
    addLog('⚠️ SSE 连接断开', '#e6a23c')
    if (eventSource) { eventSource.close(); eventSource = null }
  }
}

function disconnect() {
  if (eventSource) { eventSource.close(); eventSource = null }
}

watch(() => props.taskId, (id) => {
  if (id) { disconnect(); connect() }
})

// Auto-connect on mount
connect()
</script>
