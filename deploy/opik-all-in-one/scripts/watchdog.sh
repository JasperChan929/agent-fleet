#!/usr/bin/env bash
set -euo pipefail

terminate_supervisor() {
  local reason="$1"
  echo "[ERROR] watchdog terminating container: $reason" >&2
  if [[ -r /run/supervisord.pid ]]; then
    kill -TERM "$(cat /run/supervisord.pid)"
  fi
  exit 1
}

while [[ ! -e /run/opik/bootstrap-complete ]]; do
  if [[ -e /run/opik/bootstrap-failed ]]; then
    terminate_supervisor "bootstrap failed"
  fi
  state="$(supervisorctl status bootstrap 2>/dev/null || true)"
  if [[ "$state" == *FATAL* ]]; then
    terminate_supervisor "bootstrap entered FATAL state"
  fi
  sleep 2
done
critical=(mysql redis zookeeper minio clickhouse opik-backend nginx healthd)
while true; do
  for program in "${critical[@]}"; do
    state="$(supervisorctl status "$program" 2>/dev/null || true)"
    case "$state" in
      *RUNNING*|*STARTING*|*BACKOFF*) ;;
      *) terminate_supervisor "$program is not running: $state" ;;
    esac
  done
  sleep 5
done
