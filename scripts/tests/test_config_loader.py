import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LOADER = REPO_ROOT / "scripts/config_loader.sh"
HARBOR_ENV = REPO_ROOT / "Agents/utils/common/Harbor/env.sh"
MODEL_CONFIG_NAMES = (
    "AGENT",
    "BASE_URL",
    "ANTHROPIC_BASE_URL",
    "API_KEY",
    "AUTH_TOKEN",
    "ANTHROPIC_AUTH_TOKEN",
    "MODEL",
    "TB_MODEL",
    "TB_API_BASE",
    "TB_LLM_KWARGS",
    "TB_ANTHROPIC_BASE_URL",
    "TB_ANTHROPIC_AUTH_TOKEN",
    "TB_ANTHROPIC_MODEL",
    "TB_ANTHROPIC_DEFAULT_OPUS_MODEL",
    "TB_ANTHROPIC_DEFAULT_SONNET_MODEL",
    "TB_ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "TB_CLAUDE_CODE_SUBAGENT_MODEL",
    "HARBOR_ANALYZER_API_KEY",
    "HARBOR_ANALYZER_BASE_URL",
    "HARBOR_ANALYZER_MODEL",
    "HARBOR_RUN_TIMESTAMP",
    "HARBOR_SESSION_TIMESTAMP",
    "OPIK_PROJECT_NAME",
    "HARBOR_ZELLIJ_SESSION_NAME",
    "ROLLOUT",
    "RL_ENV_FILE",
    "RL_API_BASE",
    "RL_API_KEY",
    "RL_MODEL_NAME",
    "AGENT_FLEET_CONFIG_LOADED_ROOT",
)


class ConfigLoaderTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.config_root = self.root / "repo"
        self.config_root.mkdir()

    def tearDown(self):
        self.temp_dir.cleanup()

    def run_loader(self, script, *, extra_env=None):
        env = os.environ.copy()
        for name in MODEL_CONFIG_NAMES:
            env.pop(name, None)
        env.update(extra_env or {})
        return subprocess.run(
            [
                "bash",
                "-c",
                f'source "$1"; {script}',
                "bash",
                str(LOADER),
                str(self.config_root),
            ],
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )

    def write_configs(self, public, local):
        (self.config_root / "config.env").write_text(public, encoding="utf-8")
        (self.config_root / "config.local.env").write_text(local, encoding="utf-8")

    def test_sourced_library_enables_required_strict_mode(self):
        result = subprocess.run(
            [
                "bash",
                "-c",
                'source "$1"; [[ "$-" == *e* && "$-" == *u* && -o pipefail ]]',
                "bash",
                str(LOADER),
            ],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_saved_local_config_overrides_public_config(self):
        self.write_configs(
            "BASE_URL=https://public.example.invalid\n"
            "API_KEY=fake-public-key\n"
            "MODEL=public-model\n",
            "BASE_URL=https://saved.example.invalid\n"
            "API_KEY=fake-saved-key\n"
            "MODEL=saved-model\n",
        )

        result = self.run_loader(
            'agent_fleet_load_config "$2"; '
            'printf "%s|%s|%s" "$BASE_URL" "$API_KEY" "$MODEL"'
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout,
            "https://saved.example.invalid|fake-saved-key|saved-model",
        )

    def test_runtime_canonical_config_overrides_saved_config(self):
        self.write_configs(
            "",
            "BASE_URL=https://saved.example.invalid\n"
            "API_KEY=fake-saved-key\n"
            "MODEL=saved-model\n",
        )

        result = self.run_loader(
            'agent_fleet_load_config "$2"; '
            'printf "%s|%s|%s" "$BASE_URL" "$API_KEY" "$MODEL"',
            extra_env={
                "BASE_URL": "https://runtime.example.invalid",
                "API_KEY": "fake-runtime-key",
                "MODEL": "runtime-model",
            },
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout,
            "https://runtime.example.invalid|fake-runtime-key|runtime-model",
        )

    def test_tool_aliases_do_not_override_saved_canonical_config(self):
        self.write_configs(
            "",
            "BASE_URL=https://saved.example.invalid\n"
            "API_KEY=fake-saved-key\n"
            "MODEL=saved-model\n",
        )

        result = self.run_loader(
            'agent_fleet_load_config "$2"; '
            "agent_fleet_apply_auth_token_fallback; "
            'printf "%s|%s|%s" "$BASE_URL" "$API_KEY" "$MODEL"',
            extra_env={
                "ANTHROPIC_BASE_URL": "https://alias.example.invalid",
                "AUTH_TOKEN": "fake-auth-token",
                "ANTHROPIC_AUTH_TOKEN": "fake-anthropic-token",
                "TB_MODEL": "alias-model",
            },
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout,
            "https://saved.example.invalid|fake-saved-key|saved-model",
        )

    def test_tool_aliases_do_not_create_global_config(self):
        self.write_configs("", "")

        result = self.run_loader(
            'agent_fleet_load_config "$2"; '
            'printf "%s|%s|%s" "${BASE_URL-unset}" "${API_KEY-unset}" "${MODEL-unset}"',
            extra_env={
                "ANTHROPIC_BASE_URL": "https://alias.example.invalid",
                "AUTH_TOKEN": "fake-auth-token",
                "ANTHROPIC_AUTH_TOKEN": "fake-anthropic-token",
                "TB_MODEL": "alias-model",
            },
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "unset|unset|unset")

    def test_auth_token_fallback_is_explicit_and_fills_only_missing_api_key(self):
        self.write_configs("", "")

        result = self.run_loader(
            'agent_fleet_load_config "$2"; '
            "agent_fleet_apply_auth_token_fallback; "
            'printf "%s" "$API_KEY"',
            extra_env={"AUTH_TOKEN": "fake-auth-token"},
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "fake-auth-token")

    def test_same_root_is_loaded_only_once_per_process(self):
        self.write_configs(
            'CONFIG_LOAD_COUNT=$(( ${CONFIG_LOAD_COUNT:-0} + 1 ))\n',
            "",
        )

        result = self.run_loader(
            'agent_fleet_load_config "$2"; '
            'agent_fleet_load_config "$2"; '
            'printf "%s" "$CONFIG_LOAD_COUNT"'
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "1")

    def test_direct_harbor_uses_aliases_only_for_owned_tool_fields(self):
        env = os.environ.copy()
        for name in MODEL_CONFIG_NAMES:
            env.pop(name, None)
        env.update(
            {
                "HOME": str(self.root / "home"),
                "OUTPUT_ROOT": str(self.root / "runs"),
                "RUN_ID": "config-loader-test",
                "AGENT_FLEET_PATHS_FILE": str(self.root / "missing-paths.env"),
                "AGENT_FLEET_RUNTIME_DIR": str(self.root / "runtime"),
                # This test exercises Harbor-owned alias handling, not loading
                # the developer checkout's private configuration.
                "AGENT_FLEET_CONFIG_LOADED_ROOT": str(REPO_ROOT),
                "ANTHROPIC_BASE_URL": "https://runtime.example.invalid/v1",
                "ANTHROPIC_AUTH_TOKEN": "fake-runtime-key",
                "TB_MODEL": "runtime-model",
                "HARBOR_RUN_TIMESTAMP": "20260730-000000",
                "HARBOR_SESSION_TIMESTAMP": "000000",
                "ROLLOUT": "1",
                "TRACE_TO_OPIK": "false",
            }
        )

        result = subprocess.run(
            [
                "bash",
                "-c",
                (
                    'source "$1"; '
                    'printf "%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s" '
                    '"$BASE_URL" "$API_KEY" "$MODEL" '
                    '"$TB_ANTHROPIC_BASE_URL" "$TB_ANTHROPIC_AUTH_TOKEN" "$TB_MODEL" '
                    '"$TB_ANTHROPIC_MODEL" "$TB_ANTHROPIC_DEFAULT_OPUS_MODEL" '
                    '"$TB_ANTHROPIC_DEFAULT_SONNET_MODEL" '
                    '"$TB_ANTHROPIC_DEFAULT_HAIKU_MODEL" '
                    '"$TB_CLAUDE_CODE_SUBAGENT_MODEL" '
                    '"$TB_API_BASE" "$TB_LLM_KWARGS"; '
                    'printf "\\n%s|%s|%s|%s|%s|%s|%s|%s|%s" '
                    '"$HARBOR_ANALYZER_MODEL" "$HARBOR_ANALYZER_BASE_URL" '
                    '"$HARBOR_ANALYZER_API_KEY" "$HARBOR_RUN_MODEL_NAME" '
                    '"$OPIK_PROJECT_NAME" "$HARBOR_ZELLIJ_SESSION_NAME" '
                    '"$RL_MODEL_NAME" "$RL_API_BASE" "$RL_API_KEY"'
                ),
                "bash",
                str(HARBOR_ENV),
            ],
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        config_output, metadata_output = result.stdout.splitlines()
        self.assertEqual(
            config_output,
            "|xxx|minimax2.7|https://runtime.example.invalid"
            "|fake-runtime-key|runtime-model"
            "|runtime-model|runtime-model|runtime-model|runtime-model|runtime-model"
            '|https://runtime.example.invalid/v1/chat/completions'
            '|{"api_key":"fake-runtime-key","temperature":1.0}',
        )
        (
            analyzer_model,
            analyzer_base_url,
            analyzer_api_key,
            run_model,
            project_name,
            session_name,
            rollout_model,
            rollout_api_base,
            rollout_api_key,
        ) = metadata_output.split("|")
        self.assertEqual(analyzer_model, "runtime-model")
        self.assertEqual(
            analyzer_base_url,
            "https://runtime.example.invalid/v1",
        )
        self.assertEqual(analyzer_api_key, "fake-runtime-key")
        self.assertEqual(run_model, "runtime-model")
        self.assertEqual(
            project_name,
            "agent-fleet-claude-code-auto-runtime-model-20260730-000000",
        )
        self.assertIn("-runtime", session_name)
        self.assertNotIn("minimax", session_name)
        self.assertEqual(rollout_model, "runtime-model")
        self.assertEqual(
            rollout_api_base,
            "https://runtime.example.invalid/v1",
        )
        self.assertEqual(rollout_api_key, "fake-runtime-key")


if __name__ == "__main__":
    unittest.main()
