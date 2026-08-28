#!/usr/bin/env bash
set -euo pipefail

umask 027

: "${MYSQL_ROOT_PASSWORD:?MYSQL_ROOT_PASSWORD must be supplied as a YiCloud Secret}"
: "${MYSQL_PASSWORD:?MYSQL_PASSWORD must be supplied as a YiCloud Secret}"
: "${REDIS_PASSWORD:?REDIS_PASSWORD must be supplied as a YiCloud Secret}"
: "${CLICKHOUSE_PASSWORD:?CLICKHOUSE_PASSWORD must be supplied as a YiCloud Secret}"
: "${MINIO_ROOT_USER:?MINIO_ROOT_USER must be supplied as a YiCloud Secret}"
: "${MINIO_ROOT_PASSWORD:?MINIO_ROOT_PASSWORD must be supplied as a YiCloud Secret}"

validate_secret() {
  local name="$1"
  local value="${!name}"
  if [[ ${#value} -lt 16 || ! "$value" =~ ^[A-Za-z0-9._~!@#%^*+=:-]+$ ]]; then
    echo "[ERROR] $name must be at least 16 characters and use the documented URL-safe character set" >&2
    exit 64
  fi
}

for name in MYSQL_ROOT_PASSWORD MYSQL_PASSWORD REDIS_PASSWORD CLICKHOUSE_PASSWORD MINIO_ROOT_PASSWORD; do
  validate_secret "$name"
done

if [[ ! "$MINIO_ROOT_USER" =~ ^[A-Za-z0-9._-]{3,64}$ ]]; then
  echo "[ERROR] MINIO_ROOT_USER contains unsupported characters" >&2
  exit 64
fi

OPIK_DATA_ROOT="${OPIK_DATA_ROOT:-/mnt/shared-storage-gpfs2/opik}"
if [[ "$OPIK_DATA_ROOT" != /* ]]; then
  echo "[ERROR] OPIK_DATA_ROOT must be an absolute path" >&2
  exit 64
fi

export OPIK_DATA_ROOT
export CLICKHOUSE_DATA_PATH="$OPIK_DATA_ROOT/clickhouse/data/"
export CLICKHOUSE_ACCESS_PATH="$OPIK_DATA_ROOT/clickhouse/access/"
export CLICKHOUSE_USER_FILES_PATH="$OPIK_DATA_ROOT/clickhouse/user_files/"
export CLICKHOUSE_FORMAT_SCHEMA_PATH="$OPIK_DATA_ROOT/clickhouse/format_schemas/"
export CLICKHOUSE_PASSWORD
export STATE_DB_PROTOCOL="jdbc:mysql://"
export STATE_DB_URL="127.0.0.1:3306/opik?createDatabaseIfNotExist=true&rewriteBatchedStatements=true&connectionTimeZone=UTC&forceConnectionTimeZoneToSession=true"
export STATE_DB_DATABASE_NAME=opik
export STATE_DB_USER=opik
export STATE_DB_PASS="${STATE_DB_PASS:-$MYSQL_PASSWORD}"
export ANALYTICS_DB_MIGRATIONS_URL="jdbc:clickhouse://127.0.0.1:8123"
export ANALYTICS_DB_MIGRATIONS_USER=opik
export ANALYTICS_DB_MIGRATIONS_PASS="${ANALYTICS_DB_MIGRATIONS_PASS:-$CLICKHOUSE_PASSWORD}"
export ANALYTICS_DB_PROTOCOL=HTTP
export ANALYTICS_DB_HOST=127.0.0.1
export ANALYTICS_DB_PORT=8123
export ANALYTICS_DB_DATABASE_NAME=opik
export ANALYTICS_DB_USERNAME=opik
export ANALYTICS_DB_PASS="${ANALYTICS_DB_PASS:-$CLICKHOUSE_PASSWORD}"
export REDIS_URL="redis://:${REDIS_PASSWORD}@127.0.0.1:6379/0"
export AWS_ACCESS_KEY_ID="$MINIO_ROOT_USER"
export AWS_SECRET_ACCESS_KEY="$MINIO_ROOT_PASSWORD"
export IS_MINIO=true
export S3_URL=http://127.0.0.1:9002
export PYTHON_EVALUATOR_URL=http://127.0.0.1:8000

mkdir -p \
  "$OPIK_DATA_ROOT/mysql" \
  "$OPIK_DATA_ROOT/redis" \
  "$OPIK_DATA_ROOT/zookeeper" \
  "$OPIK_DATA_ROOT/clickhouse/data" \
  "$OPIK_DATA_ROOT/clickhouse/access" \
  "$OPIK_DATA_ROOT/clickhouse/user_files" \
  "$OPIK_DATA_ROOT/clickhouse/format_schemas" \
  "$OPIK_DATA_ROOT/minio" \
  "$OPIK_DATA_ROOT/backups" \
  /run/mysqld /run/opik /tmp/clickhouse

chown mysql:mysql "$OPIK_DATA_ROOT/mysql" /run/mysqld
chown redis:redis "$OPIK_DATA_ROOT/redis"
chown zookeeper:zookeeper "$OPIK_DATA_ROOT/zookeeper"
chown clickhouse:clickhouse \
  "$OPIK_DATA_ROOT/clickhouse" \
  "$OPIK_DATA_ROOT/clickhouse/data" \
  "$OPIK_DATA_ROOT/clickhouse/access" \
  "$OPIK_DATA_ROOT/clickhouse/user_files" \
  "$OPIK_DATA_ROOT/clickhouse/format_schemas" \
  /tmp/clickhouse
chown minio:minio "$OPIK_DATA_ROOT/minio"
chown opik:opik /run/opik

cat > /etc/opik/mysql.cnf <<EOF
[mysqld]
bind-address=127.0.0.1
port=3306
mysqlx=0
datadir=$OPIK_DATA_ROOT/mysql
socket=/run/mysqld/mysqld.sock
pid-file=/run/mysqld/mysqld.pid
skip-name-resolve=ON
innodb-buffer-pool-size=${MYSQL_INNODB_BUFFER_POOL_SIZE:-32G}
max-connections=500

[client]
socket=/run/mysqld/mysqld.sock
EOF

cat > /etc/opik/zoo.cfg <<EOF
tickTime=2000
initLimit=10
syncLimit=5
dataDir=$OPIK_DATA_ROOT/zookeeper
clientPort=2181
clientPortAddress=127.0.0.1
maxClientCnxns=60
admin.enableServer=false
4lw.commands.whitelist=ruok,srvr
EOF

chown mysql:mysql /etc/opik/mysql.cnf
chmod 0640 /etc/opik/mysql.cnf
chown zookeeper:zookeeper /etc/opik/zoo.cfg
chmod 0640 /etc/opik/zoo.cfg

mkdir -p /etc/clickhouse-server/config.d /etc/clickhouse-server/users.d
cat > /etc/clickhouse-server/config.d/99-opik-all-in-one.xml <<'EOF'
<clickhouse>
    <custom_settings_prefixes>SQL_</custom_settings_prefixes>
    <listen_host replace="replace">127.0.0.1</listen_host>
    <http_port>8123</http_port>
    <tcp_port>9000</tcp_port>
    <interserver_listen_host>127.0.0.1</interserver_listen_host>
    <path from_env="CLICKHOUSE_DATA_PATH"/>
    <tmp_path>/tmp/clickhouse/</tmp_path>
    <user_files_path from_env="CLICKHOUSE_USER_FILES_PATH"/>
    <format_schema_path from_env="CLICKHOUSE_FORMAT_SCHEMA_PATH"/>
    <uncompressed_cache_size from_env="CLICKHOUSE_UNCOMPRESSED_CACHE_SIZE"/>
    <logger>
        <level>information</level>
        <console>1</console>
        <log remove="remove"/>
        <errorlog remove="remove"/>
    </logger>
    <macros>
        <shard>1</shard>
        <replica>clickhouse</replica>
        <cluster>cluster</cluster>
    </macros>
    <zookeeper>
        <node index="1">
            <host>127.0.0.1</host>
            <port>2181</port>
        </node>
    </zookeeper>
    <zookeeper_path>/clickhouse</zookeeper_path>
    <zookeeper_session_timeout_ms>30000</zookeeper_session_timeout_ms>
    <distributed_ddl>
        <path>/clickhouse/task_queue/ddl</path>
    </distributed_ddl>
    <remote_servers>
        <cluster>
            <shard>
                <internal_replication>true</internal_replication>
                <replica>
                    <host>127.0.0.1</host>
                    <port>9000</port>
                </replica>
            </shard>
        </cluster>
    </remote_servers>
    <user_directories replace="replace">
        <users_xml>
            <path>/etc/clickhouse-server/users.xml</path>
        </users_xml>
        <local_directory>
            <path from_env="CLICKHOUSE_ACCESS_PATH"/>
        </local_directory>
    </user_directories>
</clickhouse>
EOF

cat > /etc/clickhouse-server/users.d/99-opik-all-in-one.xml <<'EOF'
<clickhouse>
    <profiles>
        <default>
            <enable_time_time64_type>1</enable_time_time64_type>
            <use_uncompressed_cache>1</use_uncompressed_cache>
        </default>
    </profiles>
    <users>
        <default>
            <networks replace="replace">
                <ip>127.0.0.1</ip>
                <ip>::1</ip>
            </networks>
        </default>
        <opik>
            <password from_env="CLICKHOUSE_PASSWORD"/>
            <networks>
                <ip>127.0.0.1</ip>
                <ip>::1</ip>
            </networks>
            <profile>default</profile>
            <quota>default</quota>
            <access_management>1</access_management>
        </opik>
    </users>
</clickhouse>
EOF

chown clickhouse:clickhouse \
  /etc/clickhouse-server/config.d/99-opik-all-in-one.xml \
  /etc/clickhouse-server/users.d/99-opik-all-in-one.xml
chmod 0640 \
  /etc/clickhouse-server/config.d/99-opik-all-in-one.xml \
  /etc/clickhouse-server/users.d/99-opik-all-in-one.xml

if [[ "${OPIK_ENFORCE_INSTANCE_LOCK:-true}" == "true" ]]; then
  exec 9>"$OPIK_DATA_ROOT/.instance.lock"
  if ! flock -n 9; then
    echo "[ERROR] another Opik all-in-one instance holds $OPIK_DATA_ROOT/.instance.lock" >&2
    exit 73
  fi
fi

rm -f /run/opik/bootstrap-complete /run/opik/bootstrap-failed
exec /usr/local/bin/supervisord -c /etc/supervisord.conf
