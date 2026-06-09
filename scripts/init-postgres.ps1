# 在宿主机 PostgreSQL 上创建 emby-soso 专用用户与数据库（Windows / PowerShell）
#
# 用法：
#   $env:DB_PASSWORD = '你的强密码'
#   .\scripts\init-postgres.ps1
#
# 可选环境变量：PG_SUPERUSER PG_HOST PG_PORT DB_NAME DB_USER DB_PASSWORD

param(
    [string]$PgSuperUser = $(if ($env:PG_SUPERUSER) { $env:PG_SUPERUSER } else { "postgres" }),
    [string]$PgHost = $(if ($env:PG_HOST) { $env:PG_HOST } else { "127.0.0.1" }),
    [int]$PgPort = $(if ($env:PG_PORT) { [int]$env:PG_PORT } else { 5432 }),
    [string]$DbName = $(if ($env:DB_NAME) { $env:DB_NAME } else { "emby_soso" }),
    [string]$DbUser = $(if ($env:DB_USER) { $env:DB_USER } else { "emby_soso" }),
    [string]$DbPassword = $(if ($env:DB_PASSWORD) { $env:DB_PASSWORD } else { "" })
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command psql -ErrorAction SilentlyContinue)) {
    throw "未找到 psql，请先安装 PostgreSQL 客户端并加入 PATH"
}

if (-not $DbPassword) {
    $DbPassword = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 24 | ForEach-Object { [char]$_ })
    Write-Host "[info] 未设置 DB_PASSWORD，已自动生成"
}

Write-Host "[info] 连接 ${PgHost}:${PgPort}，超级用户: ${PgSuperUser}"
Write-Host "[info] 将创建/更新用户: ${DbUser}，数据库: ${DbName}"

$roleSql = @"
DO `$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$DbUser') THEN
    CREATE ROLE $DbUser LOGIN PASSWORD '$DbPassword';
  ELSE
    ALTER ROLE $DbUser WITH LOGIN PASSWORD '$DbPassword';
  END IF;
END
`$\$;
"@

psql -h $PgHost -p $PgPort -U $PgSuperUser -v ON_ERROR_STOP=1 -c $roleSql

$dbExists = psql -h $PgHost -p $PgPort -U $PgSuperUser -tAc "SELECT 1 FROM pg_database WHERE datname='$DbName'"
if ($dbExists.Trim() -ne "1") {
    psql -h $PgHost -p $PgPort -U $PgSuperUser -v ON_ERROR_STOP=1 -c `
        "CREATE DATABASE $DbName OWNER $DbUser ENCODING 'UTF8' TEMPLATE template0;"
    Write-Host "[info] 已创建数据库 $DbName"
} else {
    psql -h $PgHost -p $PgPort -U $PgSuperUser -v ON_ERROR_STOP=1 -c `
        "ALTER DATABASE $DbName OWNER TO $DbUser;"
    Write-Host "[info] 数据库 $DbName 已存在，已更新 owner"
}

$grantSql = @"
GRANT ALL PRIVILEGES ON DATABASE $DbName TO $DbUser;
GRANT ALL ON SCHEMA public TO $DbUser;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO $DbUser;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO $DbUser;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO $DbUser;
"@

psql -h $PgHost -p $PgPort -U $PgSuperUser -d $DbName -v ON_ERROR_STOP=1 -c $grantSql

Write-Host ""
Write-Host "========== 完成 =========="
Write-Host "用户名:   $DbUser"
Write-Host "数据库:   $DbName"
Write-Host "密码:     $DbPassword"
Write-Host ""
Write-Host "本机连接串:"
Write-Host "  postgresql+psycopg://${DbUser}:${DbPassword}@${PgHost}:${PgPort}/${DbName}"
Write-Host ""
Write-Host "Docker 容器访问宿主机 PG:"
Write-Host "  postgresql+psycopg://${DbUser}:${DbPassword}@host.docker.internal:${PgPort}/${DbName}"
