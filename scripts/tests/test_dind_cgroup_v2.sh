#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

CGROUP_V2_ROOT="$TMP_DIR/cgroup-v2"
mkdir -p "$CGROUP_V2_ROOT"
printf '%s\n' 'cpu io memory pids' > "$CGROUP_V2_ROOT/cgroup.controllers"
printf '%s\n' 101 202 > "$CGROUP_V2_ROOT/cgroup.procs"
: > "$CGROUP_V2_ROOT/cgroup.subtree_control"

"$REPO_ROOT/scripts/dind/prepare-cgroup-v2.sh" "$CGROUP_V2_ROOT"

test -d "$CGROUP_V2_ROOT/init"
printf '%s\n' 101 202 > "$TMP_DIR/expected-procs"
cmp "$TMP_DIR/expected-procs" "$CGROUP_V2_ROOT/init/cgroup.procs"
grep -Fxq -- '+cpu +io +memory +pids' "$CGROUP_V2_ROOT/cgroup.subtree_control"

CGROUP_V1_ROOT="$TMP_DIR/cgroup-v1"
mkdir -p "$CGROUP_V1_ROOT"
"$REPO_ROOT/scripts/dind/prepare-cgroup-v2.sh" "$CGROUP_V1_ROOT"
test ! -e "$CGROUP_V1_ROOT/init"
