# Opik all-in-one for YiCloud Serving

This image is the first-integration, observability-only Opik deployment for
YiCloud Serving. It runs one replica and publishes only port `5173`. This is a
transitional deployment for environments where YiCloud does not yet provide
the Kubernetes-style multi-service orchestration used by upstream Opik. Move
back to separately managed services when that capability is available.

Included processes:

- Opik frontend and Nginx `2.2.39`
- Opik Java backend `2.2.39`
- MySQL `8.4.2`
- Redis `7.2.4`
- ClickHouse `26.3.16.16`
- ZooKeeper `3.9.4`
- MinIO and `mc` pinned to the Opik `2.2.39` Compose versions
- Supervisor, bootstrap orchestration, watchdog, and aggregate readiness

The first image intentionally excludes `opik-python-backend`, code execution,
Docker-in-Docker, guardrails, demo data, Jaeger, and the Opik OTEL profile.

## Build

```bash
image='<registry>/<project>/opik-all-in-one:2.2.39-yicloud-v1'

sudo DOCKER_BUILDKIT=0 docker build \
  --tag "$image" \
  deploy/opik-all-in-one
```

Docker Hub sources use the explicit DaoCloud prefix because Docker Hub is not
reachable from the YiCloud build host. Opik application images are pulled from
GHCR directly.

## Push to YiCloud Harbor

The Harbor quota handler currently rejects the OCI manifest emitted by Docker
29. Export the image and use `skopeo` to publish a Docker v2 schema 2 manifest.
The registry reuses blobs that are already present.

```bash
image='<registry>/<project>/opik-all-in-one:2.2.39-yicloud-v1'
archive='<archive-path>/opik-aio-2.2.39-yicloud-v1.docker.tar'
authfile='<docker-config-path>/config.json'

sudo docker save --output "$archive" "$image"
sudo skopeo copy --format v2s2 \
  --dest-authfile "$authfile" \
  "docker-archive:$archive" "docker://$image"

sudo skopeo inspect \
  --authfile "$authfile" \
  "docker://$image"
```

The expected remote media type is
`application/vnd.docker.distribution.manifest.v2+json`.

## Required secrets

Generate separate URL-safe values and inject them as YiCloud Secrets:

```text
MYSQL_ROOT_PASSWORD
MYSQL_PASSWORD
REDIS_PASSWORD
CLICKHOUSE_PASSWORD
MINIO_ROOT_USER
MINIO_ROOT_PASSWORD
```

Passwords must be at least 16 characters. Hex output from
`openssl rand -hex 32` is accepted. Do not commit or bake secret values into
the image.

## YiCloud configuration

```text
Service:       opik-observability
Replicas:      1
CPU:           64
Memory:        500 GiB
Port:          5173 only
GPFS source:   <dedicated-gpfs-source>
Mount path:    /mnt/shared-storage-gpfs2/opik
Update model:  stop-before-start / Recreate
```

Probes:

```text
Readiness:  GET /readyz on 5173
Liveness:   GET /health on 5173
```

Keep the YiCloud Startup Probe disabled for this transitional service. The
current YiCloud form rejects that probe configuration with a generic invalid
parameter error. Give Liveness a sufficiently long initial delay for the first
database initialization; verify the effective value in the YiCloud console
before changing it.

`/readyz` checks MySQL, Redis, ZooKeeper, ClickHouse, MinIO, the Opik backend,
the bootstrap marker, and Supervisor state.

## Local smoke test

Use an empty host directory and smaller memory settings on a development host:

```bash
mkdir -p /data/opik-smoke
chmod 0777 /data/opik-smoke

sudo docker run --rm --name opik-smoke \
  -p 127.0.0.1:5173:5173 \
  -v /data/opik-smoke:/mnt/shared-storage-gpfs2/opik \
  -e MYSQL_ROOT_PASSWORD='<generated>' \
  -e MYSQL_PASSWORD='<generated>' \
  -e REDIS_PASSWORD='<generated>' \
  -e CLICKHOUSE_PASSWORD='<generated>' \
  -e MINIO_ROOT_USER='<generated>' \
  -e MINIO_ROOT_PASSWORD='<generated>' \
  -e JAVA_OPTS='-Dliquibase.propertySubstitutionEnabled=true -XX:+UseG1GC -Xms1g -Xmx4g' \
  -e MYSQL_INNODB_BUFFER_POOL_SIZE=2G \
  -e CLICKHOUSE_UNCOMPRESSED_CACHE_SIZE=4294967296 \
  '<registry>/<project>/opik-all-in-one:2.2.39-yicloud-v1'
```

The test must pass `/health`, `/readyz`, UI/API access, a full restart using
the same data directory, and the no-dual-writer lock check before deployment.
