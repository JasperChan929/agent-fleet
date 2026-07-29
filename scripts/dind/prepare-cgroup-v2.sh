#!/bin/sh
# Prepare a cgroup v2 hierarchy for containers launched by nested dockerd.
set -eu

cgroup_root="${1:-/sys/fs/cgroup}"

if [ ! -f "$cgroup_root/cgroup.controllers" ]; then
  exit 0
fi

mkdir -p "$cgroup_root/init"

# A non-root cgroup cannot both contain processes and distribute domain
# controllers to children. Move DinD's own processes into /init first, then
# enable every delegated controller for the nested Docker hierarchy.
#
# Repeat because an outer `docker exec` can add a process while the initial
# process list is being drained.
while ! {
  xargs -r -n 1 < "$cgroup_root/cgroup.procs" \
    > "$cgroup_root/init/cgroup.procs" || :
  sed -e 's/ / +/g' -e 's/^/+/' \
    < "$cgroup_root/cgroup.controllers" \
    > "$cgroup_root/cgroup.subtree_control"
}; do
  :
done
