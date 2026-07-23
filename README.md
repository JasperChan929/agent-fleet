# Agent Fleet

Agent Fleet provides runnable integrations and benchmark tasksets for
evaluating Claude Code, OpenCode, and OpenClaw.

## Quick Start

### 1. Install prerequisites

- Docker with Docker Compose v2
- Python 3.9 or newer
- `git`, `curl`, `jq`, and `openssl`
- Linux `util-linux` (`flock`, `setsid`, and `script`) and `procps` (`pkill`)

These system commands must be on `PATH`; downloading an executable without
adding its directory to `PATH` is not sufficient. `setup.sh` installs the
tested Zellij and uv releases, Node.js, and Pi to user-writable locations and
records their paths for every runner. The scripts do not require tmux. Harbor
task containers still install and run the selected benchmark agent, including
Claude Code.

### 2. Clone the repository

```bash
git clone --recurse-submodules https://github.com/sii-system/agent-fleet.git
cd agent-fleet
```

### 3. Configure and set up

Run the commands below, replacing the example values with your model gateway
credentials. Opik tracing is on by default; setup persists whichever tracing
choice you make:

```bash
export BASE_URL=https://your-model-gateway.example.com  # Do not include /v1
export API_KEY=your-api-key
export MODEL=your-model-id

export TRACE_TO_OPIK=false                       # run without an Opik server
# export OPIK_URL=https://your-opik-host/api     # or keep tracing on and point it here

./scripts/setup.sh
```

After setup succeeds, this shell and future shells can invoke every public
runner without manual `PATH`, Zellij, or cache overrides. Private configuration
stays in this checkout's ignored `config.local.env`. There is no need to source
`~/.bashrc` before running the repository scripts.

### 4. Run one benchmark

Validate the environment with a one-task canary first:

```bash
TB_MIN_TEST=1 ./scripts/run_fleet.sh \
  --taskset terminalbench21 \
  --agent claude-code \
  --workers 1
```

Then start the full benchmark, with direct arguments or in natural language
(AI mode):

```bash
./scripts/run_fleet.sh --taskset terminalbench21 --agent claude-code --workers 10
./scripts/run_fleet.sh --prompt "Run terminalbench21 with claude-code and 10 workers"
```

The first run is slower while Harbor downloads the taskset and Docker images.
Rerun `setup.sh` only when configuration changes.

## FleetSpec runs

```bash
# One saved FleetSpec file
./scripts/run_fleet.sh --spec fleet-spec.json

# Multiple runs launch concurrently: one JSON array file, several files, or both
./scripts/run_fleet.sh --spec run-a.json run-b.json
```

| Flag | Short | Purpose |
| --- | --- | --- |
| `--taskset` | `-t` | Taskset to run |
| `--agent` | `-a` | `claude-code`, `opencode`, or `openclaw` |
| `--workers` | `-n` | Concurrency |
| `--prompt` | `-p` | Natural-language run request (AI mode) |
| `--spec` | `-s` | FleetSpec file(s) |
| `--output` | `-o` | Save the validated spec |
| `--dry-run` | — | Preview the commands without running |
| `--detach` | `-d` | Harbor detached mode (automatic for multi-run) |

See [scripts/README.md](./scripts/README.md) for the FleetSpec format,
tasksets, and agents.

On hosts where Docker Hub needs registry mirrors, wrap the same arguments with
the Docker-in-Docker launcher instead:

```bash
./scripts/dind-run.sh --taskset terminalbench21 --agent claude-code --workers 1
```

## More details

- Launch modes and limitations:
  [scripts/README.md](./scripts/README.md#current-limitations)
- Skills: [skills/README.md](./skills/README.md)
- Repository structure: [STRUCT.md](./STRUCT.md)
- Harbor runner: [Agents/utils/common/Harbor/STRUCT.md](./Agents/utils/common/Harbor/STRUCT.md)
