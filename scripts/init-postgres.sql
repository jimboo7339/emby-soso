-- emby-soso PostgreSQL 初始化脚本
-- 使用超级用户（postgres）执行，例如：
--   psql -U postgres -f scripts/init-postgres.sql
--
-- 执行前请修改下方密码（两处 password 保持一致）

-- ========== 1. 创建用户（已存在则只改密码） ==========
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'emby_soso') THEN
    CREATE ROLE emby_soso LOGIN PASSWORD '请替换为强密码';
    RAISE NOTICE '用户 emby_soso 已创建';
  ELSE
    ALTER ROLE emby_soso WITH LOGIN PASSWORD '请替换为强密码';
    RAISE NOTICE '用户 emby_soso 已存在，密码已更新';
  END IF;
END
$$;

-- ========== 2. 创建数据库 ==========
SELECT 'CREATE DATABASE emby_soso OWNER emby_soso ENCODING ''UTF8'' TEMPLATE template0'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'emby_soso')\gexec

-- 数据库已存在时，确保 owner 正确
ALTER DATABASE emby_soso OWNER TO emby_soso;

-- ========== 3. 授权（需连接到 emby_soso 库） ==========
\c emby_soso

GRANT ALL PRIVILEGES ON DATABASE emby_soso TO emby_soso;
GRANT ALL ON SCHEMA public TO emby_soso;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO emby_soso;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO emby_soso;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO emby_soso;

-- ========== 完成 ==========
-- 连接串示例（Docker 访问宿主机）：
-- postgresql+psycopg://emby_soso:请替换为强密码@host.docker.internal:5432/emby_soso
