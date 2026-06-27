# Novel Manager 小说管理系统

基于 Python FastAPI + Vue 3 的全栈小说资源管理平台。

## 功能

- 📚 **小说管理** — CRUD、分类标签、封面图片、状态跟踪
- 📖 **章节管理** — 富文本编辑、批量导入、拖拽排序、字数统计
- 🔍 **全文搜索** — 小说和章节内容搜索
- 🕷️ **内容爬取** — 可扩展的爬虫框架，支持多源抓取
- 🔐 **JWT 认证** — 安全的用户认证系统
- 📊 **数据仪表盘** — 小说统计、爬取任务状态

## 技术栈

| 层 | 技术 |
|---|---|
| 后端框架 | FastAPI (Python 3.12+) |
| ORM | SQLAlchemy 2.0 (异步) |
| 数据库 | SQLite / PostgreSQL |
| 认证 | JWT + bcrypt |
| 前端框架 | Vue 3 + TypeScript |
| UI 库 | Element Plus |
| 构建工具 | Vite |

## 快速开始

### Docker 部署（推荐）

```bash
docker-compose up -d
```

- 后端 API: http://localhost:8000
- API 文档: http://localhost:8000/docs
- 前端界面: http://localhost:5173

### 本地开发

**后端:**

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 复制环境配置
cp .env.example .env

# 启动服务
uvicorn app.main:app --reload --port 8000
```

**前端:**

```bash
cd frontend
npm install
npm run dev
```

### 数据库初始化

```bash
cd backend
alembic upgrade head
```

首次启动后，注册一个管理员账号即可使用。

## 项目结构

```
novel-manager/
├── backend/           # FastAPI 后端
│   ├── app/
│   │   ├── api/       # API 路由
│   │   ├── models/    # ORM 模型
│   │   ├── schemas/   # Pydantic 序列化
│   │   ├── services/  # 业务逻辑
│   │   └── crawlers/  # 爬虫框架
│   └── tests/
├── frontend/          # Vue 3 前端
│   └── src/
│       ├── views/     # 页面组件
│       ├── api/       # API 请求模块
│       ├── stores/    # Pinia 状态
│       └── router/    # 路由配置
└── docker-compose.yml
```

## API 概览

所有 API 端点前缀: `/api/v1`

- `POST /auth/register` — 注册
- `POST /auth/login` — 登录
- `GET /novels` — 小说列表（分页/筛选）
- `POST /novels` — 创建小说
- `GET /novels/{id}/chapters` — 章节列表
- `POST /crawler/trigger` — 触发爬取
- `GET /search?q=&type=` — 搜索

完整 API 文档: http://localhost:8000/docs

## License

MIT
