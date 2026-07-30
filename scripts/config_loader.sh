#!/usr/bin/env bash
# Shared repository configuration loader. This is a sourced library, not an
# entry point, so shell options and process-wide traps belong to its callers.
# It resolves source precedence only; tool-specific compatibility variables
# are interpreted by the tool that owns them.

agent_fleet_load_config() {
  local repo_root="$1"
  local entry file name
  local -a caller_env=()

  if [[ "${AGENT_FLEET_CONFIG_LOADED_ROOT:-}" == "$repo_root" ]]; then
    return 0
  fi

  # Save the runtime/exported environment before loading saved configuration.
  # compgen is a Bash builtin and works on the older Bash shipped by macOS;
  # avoid depending on the GNU-specific `env -0` option.
  while IFS= read -r name; do
    caller_env+=("$name=${!name-}")
  done < <(compgen -e)

  # Base template first, private saved configuration second.
  for file in "$repo_root/config.env" "$repo_root/config.local.env"; do
    if [[ -f "$file" ]]; then
      set -a
      # shellcheck source=/dev/null
      . "$file"
      set +a
    fi
  done

  # Runtime/exported values are the highest-priority layer.
  for entry in "${caller_env[@]}"; do
    name="${entry%%=*}"
    [[ "$name" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
    export "$entry"
  done

  AGENT_FLEET_CONFIG_LOADED_ROOT="$repo_root"
  export AGENT_FLEET_CONFIG_LOADED_ROOT
}
