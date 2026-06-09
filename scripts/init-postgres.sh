#!/usr/bin/env bash
# 在宿主机 PostgreSQL 上创建 emby-soso 专用用户与数据库
#
# 用法（需已安装 psql，并以超级用户执行）：
#   export DB_PASSWORD='你的强密码'
#   ./scripts/init-postgres.sh
#
# 或一行：
#   DB_PASSWORD='你的强密码' ./scripts/init-postgres.sh
#
# 可选环境变量：
#   PG_SUPERUSER  默认 postgres
#   PG_HOST       默认 127.0.0.1
#   PG_PORT       默认 5432
#   DB_NAME       默认 emby_soso
#   DB_USER       默认 emby_soso
#   DB_PASSWORD   必填；未设置则自动生成

set -euo pipefail

PG_SUPERUSER="${PG_SUPERUSER:-postgres}"
PG_HOST="${PG_HOST:-127.0.0.1}"
PG_PORT="${PG_PORT:-5432}"
DB_NAME="${DB_NAME:-emby_soso}"
DB_USER="${DB_USER:-emby_soso}"
DB_PASSWORD="${DB_PASSWORD:-}"

if [[ -z "$DB_PASSWORD" ]]; then
  if command -v openssl >/dev/null 2>&1; then
    DB_PASSWORD="$(openssl rand -base64 24 | tr -d '/+=' | head -c 24)"
  else
    DB_PASSWORD="$(date +%s | sha256sum | head -c 24)"
  fi
  echo "[info] 未设置 DB_PASSWORD，已自动生成"
fi

echo "[info] 连接 ${PG_HOST}:${PG_PORT}，超级用户: ${PG_SUPERUSER}"
echo "[info] 将创建/更新用户: ${DB_USER}，数据库: ${DB_NAME}"

export PGPASSWORD="${PGPASSWORD:-}"

psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_SUPERUSER" -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${DB_USER}') THEN
    CREATE ROLE ${DB_USER} LOGIN PASSWORD '${DB_PASSWORD}';
    RAISE NOTICE 'Created role ${DB_USER}';
  ELSE
    ALTER ROLE ${DB_USER} WITH LOGIN PASSWORD '${DB_PASSWORD}';
    RAISE NOTICE 'Updated password for role ${DB_USER}';
  END IF;
END
\$\$;
SQL

DB_EXISTS="$(psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_SUPERUSER" -tAc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'")"
if [[ "$DB_EXISTS" != "1" ]]; then
  psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_SUPERUSER" -v ON_ERROR_STOP=1 -c \
    "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER} ENCODING 'UTF8' TEMPLATE template0;"
  echo "[info] 已创建数据库 ${DB_NAME}"
else
  psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_SUPERUSER" -v ON_ERROR_STOP=1 -c \
    "ALTER DATABASE ${DB_NAME} OWNER TO ${DB_USER};"
  echo "[info] 数据库 ${DB_NAME} 已存在，已更新 owner"
fi

psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_SUPERUSER" -d "$DB_NAME" -v ON_ERROR_STOP=1 <<SQL
GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${DB_USER};
GRANT ALL ON SCHEMA public TO ${DB_USER};
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO ${DB_USER};
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO ${DB_USER};
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO ${DB_USER};
SQL

echo ""
echo "========== 完成 =========="
echo "用户名:   ${DB_USER}"
echo "数据库:   ${DB_NAME}"
echo "密码:     ${DB_PASSWORD}"
echo ""
echo "本机连接串:"
echo "  postgresql+psycopg://${DB_USER}:${DB_PASSWORD}@${PG_HOST}:${PG_PORT}/${DB_NAME}"
echo ""
echo "Docker 容器访问宿主机 PG（Linux 需 compose 中 extra_hosts）:"
echo "  postgresql+psycopg://${DB_USER}:${DB_PASSWORD}@host.docker.internal:${PG_PORT}/${DB_NAME}"
echo ""
echo "若密码含特殊字符 @ : / # 等，写入 .env 前请 URL 编码。"
echo "PostgreSQL 需允许 Docker 网段访问，见 scripts/pg_hba.example.conf"
