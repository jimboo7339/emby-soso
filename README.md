# emby-soso

影视文件整理、TMDB 刮削与海报墙展示。单 Docker 镜像部署，数据库默认 PostgreSQL，兼容 MySQL，Redis 可选。

## 功能概览（V1）

- **目录扫描**：递归扫描源目录，支持常规视频（mkv/mp4/…）及 **STRM** 指针文件，guessit 解析文件名；STRM 文件名信息不足时会从文件内 URL 补全
- **文件整理**：硬链接/软链接到标准影视库结构（Movies / TV Shows）
- **TMDB 刮削**：按配置项增量刮削，字段级状态追踪
- **自动匹配**：TMDB 搜索 + 置信度评分，低置信度进入待手动匹配
- **手动匹配**：前端搜索 TMDB 并绑定，支持立即刮削
- **定时任务**：APScheduler Cron 调度，任务 CRUD + 手动触发
- **海报墙**：只展示不播放，点击进入详情

## 技术栈

- 后端：Python 3.12 + FastAPI + SQLAlchemy 2.0 + Alembic + APScheduler
- 前端：Vue 3 + TypeScript + Vite + Naive UI
- 数据库：PostgreSQL（默认）/ MySQL 8
- 缓存：Redis 可选（无 Redis 时为 standalone 模式）

## 快速开始（Docker）

```bash
cp .env.example .env
# 编辑 .env，填写 TMDB_API_KEY

docker compose up -d --build
```

访问：http://localhost:8080

### 验证流程

1. 将测试视频文件放入 `./data/source/`（或通过 `SOURCE_VOLUME` 挂载 NAS 目录）
2. 打开 **任务管理**，创建任务（源路径 `/data/source`，库路径 `/data/library`）
3. 点击 **同步运行**，等待扫描 → 匹配 → 整理 → 刮削完成
4. 在 **海报墙** / **媒体列表** 查看结果；匹配失败的在详情页 **手动匹配**

## 部署模式

### 仅应用（已有 PG/MySQL/Redis）

```bash
docker compose -f docker-compose.external.yml up -d --build
```

```env
DATABASE_URL=postgresql+psycopg://user:change-me@db.example.com:5432/emby_soso
REDIS_URL=redis://redis.example.com:6379/0   # 可选
```

### MySQL

```bash
docker compose -f docker-compose.yml -f docker-compose.mysql.yml up -d --build
```

### 启用 Redis 缓存

```bash
docker compose -f docker-compose.yml -f docker-compose.redis.yml up -d --build
```

## 本地开发

### 后端

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt

# 启动 PostgreSQL 后：
set DATABASE_URL=postgresql+psycopg://emby:emby@localhost:5432/emby_soso
set TMDB_API_KEY=你的key
alembic upgrade head
uvicorn app.main:app --reload --port 8080
```

### 前端

```bash
cd frontend
npm install
npm run dev
```

开发时 Vite 将 `/api` 代理到 `http://127.0.0.1:8080`。

## 支持的文件类型

| 类型 | 扩展名 | 说明 |
|------|--------|------|
| 常规视频 | mkv, mp4, avi, mov, ts, … | 直接硬链接/软链接到影视库 |
| STRM | `.strm` | Emby/Jellyfin 流媒体指针文件，同样扫描、匹配、刮削；整理后保留 `.strm` 扩展名 |

STRM 示例：

```
# 文件名：流浪地球2 (2023).strm
# 文件内容（首行）：
http://media-server.local/video/流浪地球2.2023.2160p.mkv
```

若 STRM 文件名本身不含标题/季集信息，系统会尝试从内容 URL 的路径解析。

## 影视库目录结构

```
/data/library/
├── Movies/
│   └── 肖申克的救赎 (1994)/
│       └── 肖申克的救赎 (1994).mkv
└── TV Shows/
    └── 雨霖铃(2026) 254486/
        └── Season 01/
            └── 雨霖铃(2026) - S01E01 - 第01集.strm
```

## 任务类型

| 类型 | 说明 |
|------|------|
| `scrape_incremental` | 扫描 + 匹配 + 整理 + 增量刮削（默认） |
| `scrape_full` | 全量重刮 |
| `scan_only` | 仅扫描入库 |
| `organize_only` | 扫描 + 匹配 + 整理 |

## 环境变量

| 变量 | 说明 | 默认 |
|------|------|------|
| `DATABASE_URL` | SQLAlchemy 连接串 | `postgresql+psycopg://...` |
| `REDIS_URL` | Redis 地址（可选） | 空 |
| `TMDB_API_KEY` | TMDB API Key（可选，也可在系统设置页配置） | 空 |
| `TMDB_BASE_URL` | TMDB 或代理地址（可选，也可在系统设置页配置） | 官方 API |
| `DATA_SOURCE_ROOT` | 源媒体目录 | `/data/source` |
| `DATA_LIBRARY_ROOT` | 影视库目录 | `/data/library` |

## API 摘要

| 接口 | 说明 |
|------|------|
| `GET /api/v1/dashboard/stats` | 仪表盘统计 |
| `GET/PUT /api/v1/settings` | 刮削配置 |
| `GET/POST /api/v1/tasks` | 任务管理 |
| `POST /api/v1/tasks/{id}/run` | 后台运行任务 |
| `POST /api/v1/tasks/{id}/run/sync` | 同步运行（等待完成） |
| `GET /api/v1/media` | 媒体列表 |
| `GET /api/v1/media/{id}` | 媒体详情 |
| `GET /api/v1/media/{id}/match-context` | 手动匹配上下文 |
| `POST /api/v1/media/{id}/manual-match` | 手动匹配 |
| `POST /api/v1/media/{id}/scrape` | 单条刮削 |
| `GET /api/v1/tmdb/search` | TMDB 搜索 |

## 正式版发布与 Docker 镜像

每次在 GitHub 创建 **Release**（建议标签 `v1.0.0`）并发布后，Actions 会自动：

1. 构建多架构镜像（`linux/amd64`、`linux/arm64`）
2. 推送到 **GitHub Container Registry**：`ghcr.io/<你的用户名>/emby-soso`

### 首次使用前

1. 仓库 **Settings → Actions → General → Workflow permissions** 勾选 **Read and write permissions**
2. 仓库 **Settings → Packages** 中将包可见性设为 Public（或按需授权）
3. （可选）推送 Docker Hub：在 **Settings → Secrets** 添加
   - `DOCKERHUB_USERNAME`
   - `DOCKERHUB_TOKEN`

### 拉取镜像

```bash
# 将 OWNER/REPO 换成你的 GitHub 仓库，如 ghcr.io/myname/emby-soso:1.0.0
docker pull ghcr.io/OWNER/REPO:latest
docker run -d --name emby-soso \
  -p 8080:8080 \
  -e TMDB_API_KEY=你的key \
  -e DATABASE_URL=postgresql+psycopg://emby:change-me@postgres:5432/emby_soso \
  -v ./data/source:/data/source \
  -v ./data/library:/data/library \
  ghcr.io/OWNER/REPO:latest
```

### 手动触发构建

Actions → **Release Docker Image** → **Run workflow**，输入标签（如 `latest` 或 `1.0.0`）。

### 敏感信息说明

- **勿提交** `.env`、`backend/.env`、`data/`、数据库文件到 Git
- 本地开发：复制 `backend/.env.example` → `backend/.env`，在本地填写 TMDB Key 与路径
- 生产环境：通过 Docker / Compose **环境变量** 注入密钥，不要打进镜像
