# emby-soso

影视文件整理、TMDB 刮削与海报墙展示。单 Docker 镜像部署，数据库默认 PostgreSQL，兼容 MySQL，Redis 可选。

**GitHub：** https://github.com/jimboo7339/emby-soso  
**镜像：** `ghcr.io/jimboo7339/emby-soso`

## 功能概览

- **目录扫描**：递归扫描源目录，支持常规视频（mkv/mp4/…）及 **STRM** 指针文件，guessit 解析文件名；STRM 文件名信息不足时会从文件内 URL 补全
- **文件整理**：硬链接/软链接到标准影视库结构（Movies / TV Shows）
- **TMDB 刮削**：按配置项增量刮削，字段级状态追踪
- **自动匹配**：TMDB 搜索 + 置信度评分，低置信度进入待手动匹配
- **手动匹配**：前端搜索 TMDB 并绑定，支持立即刮削
- **定时任务**：APScheduler Cron 调度，任务 CRUD + 手动/后台运行
- **海报墙**：只展示不播放，点击进入详情

## 技术栈

- 后端：Python 3.12 + FastAPI + SQLAlchemy 2.0 + Alembic + APScheduler
- 前端：Vue 3 + TypeScript + Vite + Naive UI
- 数据库：PostgreSQL（默认）/ MySQL 8 / SQLite（本地开发）
- 缓存：Redis 可选（无 Redis 时为 standalone 模式）

## 快速开始（Docker Compose）

### 1. 准备配置

```bash
git clone git@github.com:jimboo7339/emby-soso.git
cd emby-soso
cp .env.example .env
mkdir -p data/source data/library
```

编辑 `.env`，至少填写 `TMDB_API_KEY`（也可启动后在 Web **系统设置** 中配置）。

### 2. 启动（PostgreSQL 一体栈，推荐）

**使用 Release 镜像（无需本地构建）：**

```bash
docker compose pull
docker compose up -d
```

**本地从源码构建：**

```bash
docker compose up -d --build
```

访问：http://localhost:8080

默认镜像：`ghcr.io/jimboo7339/emby-soso:latest`，可通过 `.env` 中 `EMBY_SOSO_IMAGE` 修改。

### 3. 验证流程

1. 将测试视频或 `.strm` 放入 `./data/source/`（Compose 挂载为容器内 `/data/source`）
2. 打开 **任务管理**，创建任务：
   - 源路径：`/data/source`
   - 库路径：`/data/library`
3. 点击 **同步运行**，等待扫描 → 匹配 → 整理 → 刮削
4. 在 **海报墙** / **媒体列表** 查看结果；匹配失败的在详情页 **手动匹配**

## 部署模式

| 场景 | 命令 |
|------|------|
| 默认（应用 + PostgreSQL） | `docker compose up -d` |
| 本地构建 | `docker compose up -d --build` |
| 仅应用，外接数据库 | `docker compose -f docker-compose.external.yml up -d` |
| 使用 MySQL | `docker compose -f docker-compose.yml -f docker-compose.mysql.yml up -d` |
| 启用 Redis 缓存 | `docker compose -f docker-compose.yml -f docker-compose.redis.yml up -d` |
| MySQL + Redis | 同时叠加 `docker-compose.mysql.yml` 与 `docker-compose.redis.yml` |

### 外接数据库（不含 PG 容器）

`docker-compose.external.yml` 仅启动应用，需在 `.env` 中设置 `DATABASE_URL`：

```env
DATABASE_URL=postgresql+psycopg://user:change-me@db.example.com:5432/emby_soso
REDIS_URL=redis://redis.example.com:6379/0   # 可选
```

### 单容器运行（已有数据库）

```bash
docker pull ghcr.io/jimboo7339/emby-soso:latest

docker run -d --name emby-soso \
  -p 8080:8080 \
  -e TMDB_API_KEY=你的key \
  -e DATABASE_URL=postgresql+psycopg://user:pass@host:5432/emby_soso \
  -v ./data/source:/data/source \
  -v ./data/library:/data/library \
  ghcr.io/jimboo7339/emby-soso:latest
```

## 本地开发

### 后端

```bash
cd backend
cp .env.example .env    # 默认 SQLite + ./data 相对路径
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux / macOS
pip install -r requirements.txt

alembic upgrade head
uvicorn app.main:app --reload --port 8080
```

使用 PostgreSQL 时，在 `backend/.env` 中设置 `DATABASE_URL` 和 `TMDB_API_KEY`。

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
| 常规视频 | mkv, mp4, avi, mov, ts, … | 硬链接/软链接到影视库 |
| STRM | `.strm` | Emby/Jellyfin 指针文件，整理后保留 `.strm` 扩展名 |

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
    └── 示例剧集(2026) 12345/
        └── Season 01/
            └── 示例剧集(2026) - S01E01 - 第01集.strm
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
| `EMBY_SOSO_IMAGE` | Compose 使用的应用镜像 | `ghcr.io/jimboo7339/emby-soso:latest` |
| `DATABASE_URL` | 数据库连接串 | Compose 内置 PostgreSQL |
| `REDIS_URL` | Redis 地址（可选） | 空 |
| `REDIS_ENABLED` | Redis 模式：`auto` / `true` / `false` | `auto` |
| `TMDB_API_KEY` | TMDB API Key | 空（可 Web 配置） |
| `TMDB_BASE_URL` | TMDB 或代理地址 | `https://api.themoviedb.org/3` |
| `TMDB_LANGUAGE` | TMDB 语言 | `zh-CN` |
| `DATA_SOURCE_ROOT` | 容器内源目录 | `/data/source` |
| `DATA_LIBRARY_ROOT` | 容器内影视库目录 | `/data/library` |
| `SOURCE_VOLUME` | 宿主机源目录挂载 | `./data/source` |
| `LIBRARY_VOLUME` | 宿主机库目录挂载 | `./data/library` |
| `APP_PORT` | 宿主机映射端口 | `8080` |
| `WEB_WORKERS` | Gunicorn worker 数 | `2` |

## API 摘要

| 接口 | 说明 |
|------|------|
| `GET /api/v1/health` | 健康检查 |
| `GET /api/v1/dashboard/stats` | 仪表盘统计 |
| `GET/PUT /api/v1/settings` | 系统与刮削配置 |
| `GET/POST /api/v1/tasks` | 任务管理 |
| `POST /api/v1/tasks/{id}/run` | 后台运行任务 |
| `POST /api/v1/tasks/{id}/run/sync` | 同步运行 |
| `GET /api/v1/media` | 媒体列表 |
| `GET /api/v1/media/{id}` | 媒体详情 |
| `POST /api/v1/media/{id}/manual-match` | 手动匹配 |
| `POST /api/v1/media/{id}/scrape` | 单条刮削 |
| `GET /api/v1/tmdb/search` | TMDB 搜索 |

## 正式版发布与 CI

在 GitHub 创建 **Release**（标签建议 `v1.0.0`）并发布后，Actions 工作流 **Release Docker Image** 会：

1. 构建多架构镜像（`linux/amd64`、`linux/arm64`）
2. 推送到 GHCR：`ghcr.io/jimboo7339/emby-soso:<版本>`

标签规则（以 Release `v1.2.3` 为例）：

- `ghcr.io/jimboo7339/emby-soso:1.2.3`
- `ghcr.io/jimboo7339/emby-soso:1.2`
- `ghcr.io/jimboo7339/emby-soso:1`
- 非预发布版本额外打 `latest`

### CI 首次配置

1. **Settings → Actions → General** → Workflow permissions 选 **Read and write permissions**
2. **Settings → Packages** → 将包设为 Public（或按需授权拉取）
3. （可选 Docker Hub）添加 Secrets：`DOCKERHUB_USERNAME`、`DOCKERHUB_TOKEN`

### 手动触发构建

Actions → **Release Docker Image** → **Run workflow**，输入标签（如 `latest`）。

## 安全说明

- **勿提交** `.env`、`backend/.env`、`data/`、数据库文件到 Git
- 本地开发：复制 `backend/.env.example` → `backend/.env`
- 生产环境：通过 Compose / `docker run` **环境变量** 注入密钥，不要写入镜像
