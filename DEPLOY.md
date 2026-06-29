# Novel Manager 部署安装指南

## 系统要求

| 组件 | 最低配置 | 推荐配置 |
|------|---------|---------|
| CPU | 2 核 | 4 核+ |
| 内存 | 2 GB | 8 GB+ |
| 磁盘 | 20 GB | 100 GB+ (小说内容存储) |
| 系统 | Linux/macOS/Windows | Linux (Ubuntu 22.04) |

## 架构概览

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   Nginx      │───▶│  FastAPI × N │───▶│    MySQL     │
│   :80/:443   │    │  :8008       │    │    :3306     │
└──────────────┘    └──────────────┘    └──────────────┘
       │                   │                    │
       │                   ├─ Redis :6379      │
       │                   ├─ Queue Runner      │
       │                   └─ Watchdog          │
       ▼
┌──────────────┐
│   Vue 3      │
│   :5173      │
└──────────────┘
```

---

## 方式一：Docker Compose 部署（推荐）

### 1. 克隆项目

```bash
git clone https://github.com/u4399com-beep/novel-manager.git
cd novel-manager
```

### 2. 配置环境变量

```bash
cp backend/.env.example backend/.env
# 编辑 backend/.env
```

`.env` 内容：
```env
DATABASE_URL=mysql+asyncmy://root:password@mysql:3306/novel_manager
SECRET_KEY=your-random-secret-key-here
ACCESS_TOKEN_EXPIRE_MINUTES=480
CORS_ORIGINS=["http://localhost:5173","http://localhost:3000","http://localhost"]
```

### 3. 启动所有服务

```bash
docker-compose up -d
```

服务端口：
- 后端 API: http://localhost:8008
- 前端界面: http://localhost:5173
- API 文档: http://localhost:8008/docs
- MySQL: localhost:3306
- Redis: localhost:6379

### 4. 初始化数据库

```bash
docker-compose exec backend alembic upgrade head
```

### 5. 启动采集队列

```bash
docker-compose exec backend python3 queue_runner.py --concurrent 8
```

### 6. 启动看门狗

```bash
docker-compose exec backend python3 queue_watchdog.py
```

---

## 方式二：Linux 手动部署

### Ubuntu 22.04 / Debian 12

#### 1. 安装依赖

```bash
# 系统依赖
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3-pip \
    mysql-server redis-server nginx nodejs npm git curl

# 启动 MySQL + Redis
sudo systemctl enable --now mysql redis-server

# 创建数据库
sudo mysql -e "CREATE DATABASE novel_manager CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
sudo mysql -e "CREATE USER 'novel'@'localhost' IDENTIFIED BY 'your-password';"
sudo mysql -e "GRANT ALL ON novel_manager.* TO 'novel'@'localhost';"
```

#### 2. 部署后端

```bash
cd /opt
git clone https://github.com/u4399com-beep/novel-manager.git
cd novel-manager/backend

# 虚拟环境
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 配置
cp .env.example .env
# 编辑 .env: 填写 MySQL 连接信息和 SECRET_KEY

# 数据库迁移
alembic upgrade head

# 启动 (生产环境用 gunicorn)
pip install gunicorn
gunicorn -k uvicorn.workers.UvicornWorker \
  -w 4 --bind 0.0.0.0:8008 \
  --timeout 300 --keep-alive 5 \
  app.main:app
```

#### 3. 部署前端

```bash
cd /opt/novel-manager/frontend
npm install
npm run build

# 配置 Nginx
sudo tee /etc/nginx/sites-available/novel-manager << 'NGINX'
server {
    listen 80;
    server_name your-domain.com;

    # 前端静态文件
    root /opt/novel-manager/frontend/dist;
    index index.html;

    # API 代理
    location /api/ {
        proxy_pass http://127.0.0.1:8008;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /static/ {
        proxy_pass http://127.0.0.1:8008;
    }

    # Vue Router 回退
    location / {
        try_files $uri $uri/ /index.html;
    }
}
NGINX

sudo ln -s /etc/nginx/sites-available/novel-manager /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

#### 4. Systemd 服务

```bash
# 后端服务
sudo tee /etc/systemd/system/novel-backend.service << 'SERVICE'
[Unit]
Description=Novel Manager Backend
After=network.target mysql.service redis.service

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/novel-manager/backend
ExecStart=/opt/novel-manager/backend/venv/bin/gunicorn -k uvicorn.workers.UvicornWorker -w 4 --bind 127.0.0.1:8008 app.main:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE

# 队列服务
sudo tee /etc/systemd/system/novel-queue.service << 'SERVICE'
[Unit]
Description=Novel Manager Queue Runner
After=novel-backend.service

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/novel-manager/backend
ExecStart=/opt/novel-manager/backend/venv/bin/python3 queue_runner.py --concurrent 8
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SERVICE

# 看门狗服务
sudo tee /etc/systemd/system/novel-watchdog.service << 'SERVICE'
[Unit]
Description=Novel Manager Watchdog
After=novel-queue.service

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/novel-manager/backend
ExecStart=/opt/novel-manager/backend/venv/bin/python3 queue_watchdog.py
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
SERVICE

sudo systemctl daemon-reload
sudo systemctl enable --now novel-backend novel-queue novel-watchdog
```

#### 5. 安装 LibreTranslate（可选）

```bash
docker run -d --name libretranslate \
  -p 5001:5000 \
  --restart unless-stopped \
  libretranslate/libretranslate:v1.9.5
```

---

## 方式三：macOS 部署

### 1. 安装依赖

```bash
# Homebrew
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 安装服务
brew install python@3.11 mysql redis node git

# 启动服务
brew services start mysql
brew services start redis

# 创建数据库
mysql -u root -e "CREATE DATABASE novel_manager CHARACTER SET utf8mb4;"
mysql -u root -e "CREATE USER 'novel'@'localhost' IDENTIFIED BY 'password';"
mysql -u root -e "GRANT ALL ON novel_manager.* TO 'novel'@'localhost';"
```

### 2. 部署后端

```bash
cd ~/
git clone https://github.com/u4399com-beep/novel-manager.git
cd novel-manager/backend

python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# 编辑 .env

alembic upgrade head

# 启动
python3 -m uvicorn app.main:app --port 8008 --log-level warning &
python3 queue_runner.py --concurrent 8 &
python3 queue_watchdog.py &
```

### 3. 部署前端

```bash
cd ~/novel-manager/frontend
npm install
npm run dev -- --port 5173 &
```

### 4. 开机自启 (launchd)

```bash
# 创建启动脚本
cat > ~/novel-manager/start.sh << 'EOF'
#!/bin/bash
cd "$(dirname "$0")/backend"
source venv/bin/activate
python3 -m uvicorn app.main:app --port 8008 --log-level warning &
python3 queue_runner.py --concurrent 8 &
python3 queue_watchdog.py &
cd ../frontend
npm run dev -- --port 5173 &
EOF
chmod +x ~/novel-manager/start.sh

# 登录自动启动: 系统偏好设置 → 用户与群组 → 登录项 → 添加 start.sh
```

---

## 方式四：Windows 部署

### 1. 安装依赖

```powershell
# 安装 Python 3.11+: https://www.python.org/downloads/
# 安装 Node.js 18+:  https://nodejs.org/
# 安装 MySQL 8.0:   https://dev.mysql.com/downloads/installer/
# 安装 Redis:        https://github.com/tporadowski/redis/releases
# 安装 Git:          https://git-scm.com/download/win
```

### 2. 部署后端

```powershell
cd C:\
git clone https://github.com/u4399com-beep/novel-manager.git
cd novel-manager\backend

python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

copy .env.example .env
# 编辑 .env 配置数据库

alembic upgrade head

# 启动 (3 个终端窗口)
# 终端 1: 后端
venv\Scripts\python -m uvicorn app.main:app --port 8008

# 终端 2: 队列
venv\Scripts\python queue_runner.py --concurrent 8

# 终端 3: 看门狗
venv\Scripts\python queue_watchdog.py
```

### 3. 部署前端

```powershell
cd C:\novel-manager\frontend
npm install
npm run dev -- --port 5173
```

### 4. 生产部署 (IIS + Nginx)

使用 Nginx for Windows 或 IIS 反向代理：

```nginx
# nginx.conf
server {
    listen 80;
    root C:/novel-manager/frontend/dist;

    location /api/ {
        proxy_pass http://127.0.0.1:8008;
    }

    location / {
        try_files $uri /index.html;
    }
}
```

---

## 初始化配置

### 1. 注册管理员

访问 http://your-server:5173 → 注册账号（第一个注册的即为管理员）

### 2. 配置站点

登录后进入「站群管理」→ 添加站点：
- 域名: `your-domain.com`
- 模板: `default`（可选 biquge/daquan/teezi 等 6 套主题）
- 语言: 选择 29 种语言之一

### 3. 配置采集规则

「采集规则编辑器」→ 选择 `23qb` 规则 → 测试 → 保存

### 4. 开始采集

仪表盘 → 批量添加书籍 ID → 队列自动采集

---

## 环境变量参考

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DATABASE_URL` | `mysql+asyncmy://root:password@localhost:3306/novel_manager` | 数据库连接 |
| `SECRET_KEY` | `change-me` | JWT 密钥 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `480` | 登录有效期(分钟) |
| `CORS_ORIGINS` | `["http://localhost:5173"]` | 允许的跨域来源 |
| `CRAWLER_REQUEST_DELAY` | `0.2` | 采集请求间隔(秒) |
| `CRAWLER_TIMEOUT` | `60` | 采集超时(秒) |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis 连接 |

---

## 性能调优

### MySQL

```sql
-- my.cnf
innodb_buffer_pool_size = 2G
innodb_log_file_size = 512M
max_connections = 200
```

### Gunicorn

```bash
# 根据 CPU 核数调整 worker 数量
gunicorn -w $(nproc) -k uvicorn.workers.UvicornWorker app.main:app
```

### 缓存

- Redis 缓存: 自动启用（REDIS_URL 配置）
- 内存缓存: Redis 不可用时自动降级（LRU 500条）

---

## 常用命令

```bash
# 查看采集队列
curl http://localhost:8008/api/v1/watchdog/status

# 重启队列
curl -X POST http://localhost:8008/api/v1/watchdog/restart

# 数据库迁移
cd backend && alembic upgrade head

# 修复空章节
cd backend && python3 repair_empty_chapters.py

# 修复封面图
cd backend && python3 repair_covers.py

# 修复 Book-XXXX 占位名
cd backend && python3 repair_placeholders.py --fix

# 查看日志
tail -f /tmp/queue_runner.log
tail -f /tmp/watchdog.log
tail -f /tmp/backend.log
```
