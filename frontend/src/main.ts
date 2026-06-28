import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import zhCn from 'element-plus/dist/locale/zh-cn.mjs'
import {
  Odometer, Reading, Collection, Download, Monitor, Setting,
  Connection, Plus, RefreshRight, Search,
} from '@element-plus/icons-vue'

import App from './App.vue'
import router from './router'
import './style.css'

const app = createApp(App)

app.use(createPinia())
app.use(router)
app.use(ElementPlus, { locale: zhCn })

// Register only the used Element Plus icons
const icons: Record<string, any> = {
  Odometer, Reading, Collection, Download, Monitor, Setting,
  Connection, Plus, RefreshRight, Search,
}
for (const [key, component] of Object.entries(icons)) {
  app.component(key, component)
}

app.mount('#app')
