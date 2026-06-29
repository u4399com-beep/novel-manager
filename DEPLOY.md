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

```

---

## 方式五：飞牛云 FNS (FNOS) 部署

飞牛云 FNS 是基于 Debian 的 NAS 操作系统，支持 Docker 和手动部署两种方式。

### 环境信息

| 项目 | 说明 |
|------|------|
| 系统 | FNS (FNOS) 基于 Debian 12 |
| 架构 | x86_64 / ARM64 |
| 默认 Web 端口 | 5666 (FNS 管理界面) |
| 建议部署方式 | Docker Compose |

### 5.1 Docker Compose 部署（推荐）

#### 1. 开启 SSH

FNS 管理界面 → 设置 → 终端 → 开启 SSH → 记录端口（默认 22）

```bash
ssh your-nas-ip -p 22
```

#### 2. 创建项目目录

```bash
# 建议放在数据卷上（空间充足）
mkdir -p /vol1/docker/novel-manager
cd /vol1/docker/novel-manager
```

#### 3. 创建 docker-compose.yml

```bash
cat > docker-compose.yml << 'EOF'
version: "3.8"

services:
  mysql:
    image: mysql:8.0
    container_name: novel-mysql
    restart: unless-stopped
    environment:
      MYSQL_ROOT_PASSWORD: NovelManager@2024
      MYSQL_DATABASE: novel_manager
      MYSQL_CHARSET: utf8mb4
      MYSQL_COLLATION: utf8mb4_unicode_ci
    volumes:
      - ./mysql-data:/var/lib/mysql
    ports:
      - "3306:3306"
    command: --character-set-server=utf8mb4 --collation-server=utf8mb4_unicode_ci

  redis:
    image: redis:7-alpine
    container_name: novel-redis
    restart: unless-stopped
    ports:
      - "6379:6379"
    volumes:
      - ./redis-data:/data

  backend:
    image: python:3.11-slim
    container_name: novel-backend
    restart: unless-stopped
    working_dir: /app
    command: >
      sh -c "pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple &&
             alembic upgrade head &&
             gunicorn -k uvicorn.workers.UvicornWorker -w 2 --bind 0.0.0.0:8008 app.main:app"
    ports:
      - "8008:8008"
    volumes:
      - ./backend:/app
      - ./data:/app/data
    environment:
      - DATABASE_URL=mysql+asyncmy://root:NovelManager@2024@mysql:3306/novel_manager
      - SECRET_KEY=fns-novel-manager-secret-key-change-me
      - CORS_ORIGINS=["http://your-nas-ip:5173","http://localhost:5173"]
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - mysql
      - redis

  queue:
    image: python:3.11-slim
    container_name: novel-queue
    restart: unless-stopped
    working_dir: /app
    command: >
      sh -c "pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple &&
             python3 queue_runner.py --concurrent 5"
    volumes:
      - ./backend:/app
      - ./data:/app/data
    environment:
      - DATABASE_URL=mysql+asyncmy://root:NovelManager@2024@mysql:3306/novel_manager
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - mysql
      - redis

  watchdog:
    image: python:3.11-slim
    container_name: novel-watchdog
    restart: unless-stopped
    working_dir: /app
    command: >
      sh -c "pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple &&
             python3 queue_watchdog.py"
    volumes:
      - ./backend:/app
    environment:
      - DATABASE_URL=mysql+asyncmy://root:NovelManager@2024@mysql:3306/novel_manager
    depends_on:
      - mysql

  frontend:
    image: node:20-alpine
    container_name: novel-frontend
    restart: unless-stopped
    working_dir: /app
    command: >
      sh -c "npm config set registry https://registry.npmmirror.com &&
             npm install &&
             npm run dev -- --host 0.0.0.0 --port 5173"
    ports:
      - "5173:5173"
    volumes:
      - ./frontend:/app
    depends_on:
      - backend

  # LibreTranslate (可选 — 内容翻译)
  libretranslate:
    image: libretranslate/libretranslate:v1.9.5
    container_name: novel-translate
    restart: unless-stopped
    ports:
      - "5001:5000"
EOF
```

#### 4. 拉取代码并启动

```bash
# 克隆项目
git clone https://github.com/u4399com-beep/novel-manager.git /tmp/novel-manager
cp -r /tmp/novel-manager/backend ./
cp -r /tmp/novel-manager/frontend ./
rm -rf /tmp/novel-manager

# 创建内容存储目录
mkdir -p data/content

# 启动
docker-compose up -d

# 查看日志
docker-compose logs -f
```

#### 5. 访问

```
后端:   http://your-nas-ip:8008
前端:   http://your-nas-ip:5173
API文档: http://your-nas-ip:8008/docs
```

---

### 5.2 FNS Docker 应用商店部署

FNS 支持 Docker 应用一键部署：

1. 打开 FNS 管理界面 → **Docker** → **应用商店**
2. 点击 **添加应用** → **Compose**
3. 粘贴上面的 `docker-compose.yml` 内容
4. 点击 **部署**
5. 等待容器启动完成

---

### 5.3 手动部署（Debian 底层）

FNS 基于 Debian，可通过 SSH 手动部署：

```bash
# SSH 登录 FNS
ssh your-nas-ip

# 安装 Docker（如果未安装）
curl -fsSL https://get.docker.com | sh

# 安装 Docker Compose
apt update && apt install -y docker-compose git

# 后续步骤同 "5.1 Docker Compose 部署"
```

---

### 5.4 FNS 端口说明

FNS 默认占用以下端口，避免冲突：

| 端口 | 服务 | 说明 |
|------|------|------|
| 5666 | FNS 管理 | 系统保留 |
| 8000 | FNS 应用 | 可能占用，项目改用 8008 |
| 8008 | Novel 后端 | ✅ 本项目 |
| 5173 | Novel 前端 | ✅ 本项目 |
| 3306 | MySQL | ✅ 数据库 |
| 6379 | Redis | ✅ 缓存 |
| 5001 | LibreTranslate | 可选 |

---

### 5.5 FNS 外网访问

通过 FNS 自带的内网穿透或 DDNS 实现外网访问：

**方式 A — FNS 内网穿透**：
FNS 管理 → 网络 → 内网穿透 → 添加映射：
```
本地端口 5173 → 外网端口 5173
本地端口 8008 → 外网端口 8008
```

**方式 B — 反代 + DDNS**：
```bash
# 安装 Nginx
apt install -y nginx

# 配置反代 (参考 "方式二 Linux 部署" 中的 Nginx 配置)
# 配合 DDNS 实现域名访问
```

---

### 5.6 FNS 定时任务

在 FNS 管理界面设置 cron 定时任务：

```bash
# 每天凌晨 3 点重启看门狗（防止僵死）
0 3 * * * docker restart novel-watchdog

# 每周日凌晨 4 点备份数据库
0 4 * * 0 docker exec novel-mysql mysqldump -uroot -pNovelManager@2024 novel_manager > /vol1/backup/novel_$(date +\%Y\%m\%d).sql
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
