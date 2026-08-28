#!/usr/bin/env bash
set -euo pipefail

trap 'status=$?; touch /run/opik/bootstrap-failed; echo "[ERROR] bootstrap failed with status $status" >&2; exit "$status"' ERR

wait_until() {
  local name="$1"
  local attempts="$2"
  shift 2
  local attempt
  for ((attempt = 1; attempt <= attempts; attempt++)); do
    if "$@" >/dev/null 2>&1; then
      echo "[INFO] $name is ready"
      return 0
    fi
    sleep 2
  done
  echo "[ERROR] timed out waiting for $name" >&2
  return 1
}

mysql_root_ready() {
  /usr/bin/mysqladmin --protocol=socket --socket=/run/mysqld/mysqld.sock -uroot ping
}

mysql_opik_ready() {
  MYSQL_PWD="$MYSQL_PASSWORD" /usr/bin/mysqladmin --protocol=tcp -h127.0.0.1 -P3306 -uopik ping
}

redis_ready() {
  REDISCLI_AUTH="$REDIS_PASSWORD" /usr/local/bin/redis-cli -h 127.0.0.1 -p 6379 ping | grep -qx PONG
}

zookeeper_ready() {
  printf ruok | nc -w 2 127.0.0.1 2181 | grep -qx imok
}

clickhouse_ready() {
  curl -fsS --max-time 2 http://127.0.0.1:8123/ping | grep -q Ok
}

minio_ready() {
  curl -fsS --max-time 3 http://127.0.0.1:9002/minio/health/live
}

backend_ready() {
  curl -fsS --max-time 5 http://127.0.0.1:8080/health-check
}

fresh_mysql=0
if [[ ! -d "$OPIK_DATA_ROOT/mysql/mysql" ]]; then
  echo "[INFO] initializing MySQL data directory"
  runuser -u mysql -- /usr/sbin/mysqld --defaults-file=/etc/opik/mysql.cnf --initialize-insecure
  fresh_mysql=1
fi

supervisorctl start mysql
if [[ "$fresh_mysql" == 1 ]]; then
  wait_until mysql 180 mysql_root_ready
  /usr/bin/mysql --protocol=socket --socket=/run/mysqld/mysqld.sock -uroot <<SQL
ALTER USER 'root'@'localhost' IDENTIFIED BY '${MYSQL_ROOT_PASSWORD}';
CREATE DATABASE IF NOT EXISTS opik CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'opik'@'%' IDENTIFIED BY '${MYSQL_PASSWORD}';
ALTER USER 'opik'@'%' IDENTIFIED BY '${MYSQL_PASSWORD}';
GRANT ALL PRIVILEGES ON opik.* TO 'opik'@'%';
FLUSH PRIVILEGES;
SQL
else
  wait_until mysql 180 mysql_opik_ready
fi
wait_until mysql-opik 60 mysql_opik_ready

supervisorctl start redis
supervisorctl start zookeeper
supervisorctl start minio
wait_until redis 90 redis_ready
wait_until zookeeper 180 zookeeper_ready
wait_until minio 90 minio_ready

supervisorctl start clickhouse
wait_until clickhouse 300 clickhouse_ready
/usr/bin/clickhouse-client --host 127.0.0.1 --port 9000 \
  --user opik --password "$CLICKHOUSE_PASSWORD" \
  --query 'CREATE DATABASE IF NOT EXISTS opik'

/usr/local/bin/mc alias set local http://127.0.0.1:9002 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD"
/usr/local/bin/mc mb --ignore-existing local/public
/usr/local/bin/mc anonymous set download local/public

echo "[INFO] running Opik database migrations"
runuser -u opik -p -- /bin/bash -lc 'cd /opt/opik && ./run_db_migrations.sh && ./provision_agent_insights_readonly_user.sh'

supervisorctl start opik-backend
wait_until opik-backend 300 backend_ready

supervisorctl start nginx
wait_until nginx 30 curl -fsS --max-time 3 http://127.0.0.1:5173/health

touch /run/opik/bootstrap-complete
rm -f /run/opik/bootstrap-failed
echo "[INFO] Opik all-in-one bootstrap completed"
