# syntax=docker/dockerfile:1

FROM ghcr.io/comet-ml/opik/opik-backend@sha256:83fb1df6048bc0792ecc2a3a0294774fcd838c7ff277ec86748c401ab173c41c AS opik-backend
FROM ghcr.io/comet-ml/opik/opik-frontend@sha256:f86b287af5a58ace543f00a629ac5bcef2f500c816f0f102ba4f2acf98b1771b AS opik-frontend
FROM docker.m.daocloud.io/clickhouse/clickhouse-server@sha256:014015f09cfc047fcc45ed64216812b7a37225526597d090950f6694e82259f3 AS clickhouse
FROM docker.m.daocloud.io/library/zookeeper@sha256:dfa9ba46d14bd52bcb3c1dac3ba91f179cf4cebf7ee576e1c2df09c68fc1d30d AS zookeeper
FROM docker.m.daocloud.io/minio/minio@sha256:46b3009bf7041eefbd90bd0d2b38c6ddc24d20a35d609551a1802c558c1c958f AS minio
FROM docker.m.daocloud.io/minio/mc@sha256:470f5546b596e16c7816b9c3fa7a78ce4076bb73c2c73f7faeec0c8043923123 AS minio-client

FROM docker.m.daocloud.io/library/mysql@sha256:ac80b6e09e5b12b4f9d5cd4f6425e43464247aa4ba4f6169da5daf59e5877f7d AS redis-builder
ARG REDIS_VERSION=7.2.4
RUN microdnf install -y curl tar gzip gcc make ca-certificates \
    && microdnf clean all \
    && curl -fsSLo /tmp/redis.tar.gz "https://download.redis.io/releases/redis-${REDIS_VERSION}.tar.gz" \
    && mkdir -p /tmp/redis /out \
    && tar -xzf /tmp/redis.tar.gz -C /tmp/redis --strip-components=1 \
    && make -C /tmp/redis -j2 MALLOC=libc BUILD_TLS=no \
    && install -m 0755 \
       /tmp/redis/src/redis-server \
       /tmp/redis/src/redis-cli \
       /tmp/redis/src/redis-sentinel \
       /out/

FROM docker.m.daocloud.io/library/mysql@sha256:ac80b6e09e5b12b4f9d5cd4f6425e43464247aa4ba4f6169da5daf59e5877f7d

ARG OPIK_VERSION=2.2.39

LABEL org.opencontainers.image.title="Opik all-in-one for YiCloud" \
      org.opencontainers.image.description="Single-container observability-only Opik deployment for YiCloud Serving" \
      org.opencontainers.image.version="${OPIK_VERSION}-yicloud-v1" \
      org.opencontainers.image.source="https://github.com/sii-system/agent-fleet"

RUN microdnf install -y \
      bash ca-certificates curl findutils gzip hostname iproute jq \
      nmap-ncat nginx openssl procps-ng python3 python3-pip shadow-utils tar \
      util-linux which \
    && microdnf clean all \
    && pip3 install --no-cache-dir supervisor==4.2.5

RUN groupadd --system redis \
    && useradd --system --gid redis --home-dir /nonexistent --shell /sbin/nologin redis \
    && groupadd --system clickhouse \
    && useradd --system --gid clickhouse --home-dir /nonexistent --shell /sbin/nologin clickhouse \
    && groupadd --system zookeeper \
    && useradd --system --gid zookeeper --home-dir /opt/zookeeper --shell /sbin/nologin zookeeper \
    && groupadd --system minio \
    && useradd --system --gid minio --home-dir /nonexistent --shell /sbin/nologin minio \
    && groupadd --gid 1001 opik \
    && useradd --uid 1001 --gid 1001 --home-dir /opt/opik --shell /sbin/nologin opik \
    && mkdir -p /etc/opik /run/opik /var/lib/opik-frontend

COPY --from=redis-builder /out/redis-server /out/redis-cli /out/redis-sentinel /usr/local/bin/
COPY --from=clickhouse /usr/bin/clickhouse /usr/bin/clickhouse
COPY --from=clickhouse /etc/clickhouse-server /etc/clickhouse-server
COPY --from=zookeeper --chown=zookeeper:zookeeper /apache-zookeeper-3.9.4-bin /opt/zookeeper
COPY --from=minio /usr/bin/minio /usr/local/bin/minio
COPY --from=minio-client /usr/bin/mc /usr/local/bin/mc
COPY --from=opik-backend /usr/lib/jvm/java-25-amazon-corretto.x86_64 /usr/lib/jvm/java-25-amazon-corretto.x86_64
COPY --from=opik-backend --chown=1001:1001 /opt/opik /opt/opik
COPY --from=opik-frontend --chown=nginx:nginx /usr/share/nginx/html /var/lib/opik-frontend

COPY configs/nginx.conf /etc/nginx/nginx.conf
COPY configs/supervisord.conf /etc/supervisord.conf
COPY scripts/entrypoint.sh /usr/local/bin/opik-entrypoint
COPY scripts/bootstrap.sh /usr/local/bin/opik-bootstrap
COPY scripts/watchdog.sh /usr/local/bin/opik-watchdog
COPY scripts/healthd.py /usr/local/bin/opik-healthd

RUN chmod 0755 \
      /usr/local/bin/opik-entrypoint \
      /usr/local/bin/opik-bootstrap \
      /usr/local/bin/opik-watchdog \
      /usr/local/bin/opik-healthd \
      /usr/local/bin/minio \
      /usr/local/bin/mc \
    && mkdir -p /var/cache/nginx /var/log/nginx \
    && ln -sf /usr/lib/jvm/java-25-amazon-corretto.x86_64/bin/java /usr/local/bin/java \
    && ln -sf /usr/bin/clickhouse /usr/bin/clickhouse-server \
    && ln -sf /usr/bin/clickhouse /usr/bin/clickhouse-client \
    && rm -f /etc/clickhouse-server/config.d/docker_related_config.xml \
    && sed -i '/port: ${SERVER_APPLICATION_PORT:-8080}/a\      bindHost: 127.0.0.1' /opt/opik/config.yml \
    && sed -i '/port: ${SERVER_ADMIN_PORT:-8081}/a\      bindHost: 127.0.0.1' /opt/opik/config.yml \
    && sed -i 's/jwebserver -d \/opt\/opik\/redoc -b 0\.0\.0\.0 -p 3003/jwebserver -d \/opt\/opik\/redoc -b 127.0.0.1 -p 3003/' /opt/opik/entrypoint.sh \
    && grep -q 'bindHost: 127.0.0.1' /opt/opik/config.yml \
    && grep -q 'jwebserver -d /opt/opik/redoc -b 127.0.0.1 -p 3003' /opt/opik/entrypoint.sh \
    && chown -R clickhouse:clickhouse /etc/clickhouse-server \
    && chmod -R go-w /etc/clickhouse-server \
    && chown -R opik:opik /opt/opik \
    && chown -R nginx:nginx /var/lib/opik-frontend /var/cache/nginx /var/log/nginx \
    && rm -f /etc/nginx/conf.d/default.conf

ENV OPIK_VERSION=2.2.39 \
    OPIK_DATA_ROOT=/mnt/shared-storage-gpfs2/opik \
    JAVA_HOME=/usr/lib/jvm/java-25-amazon-corretto.x86_64 \
    PATH=/usr/lib/jvm/java-25-amazon-corretto.x86_64/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    JAVA_OPTS="-Dliquibase.propertySubstitutionEnabled=true -XX:+UseG1GC -Xms8g -Xmx64g" \
    OPIK_USAGE_REPORT_ENABLED=false \
    OPIK_OTEL_SDK_ENABLED=false \
    TOGGLE_OPIK_AI_ENABLED=false \
    TOGGLE_GUARDRAILS_ENABLED=false \
    TOGGLE_OLLIE_ENABLED=false \
    TOGGLE_WELCOME_WIZARD_ENABLED=false \
    TOGGLE_PYTHON_EVALUATOR_ENABLED=false \
    TOGGLE_TRACE_THREAD_PYTHON_EVALUATOR_ENABLED=false \
    ANALYTICS_DB_CLUSTER_HEALTH_CHECK_ENABLED=false \
    ANALYTICS_DB_COLD_STORAGE_DISK_HEALTH_CHECK_ENABLED=false \
    CLICKHOUSE_UNCOMPRESSED_CACHE_SIZE=68719476736 \
    MYSQL_INNODB_BUFFER_POOL_SIZE=32G \
    OPIK_ENFORCE_INSTANCE_LOCK=true

EXPOSE 5173
STOPSIGNAL SIGTERM
HEALTHCHECK --interval=30s --timeout=5s --start-period=180s --retries=3 \
  CMD curl -fsS http://127.0.0.1:5173/health || exit 1

ENTRYPOINT ["/usr/local/bin/opik-entrypoint"]
