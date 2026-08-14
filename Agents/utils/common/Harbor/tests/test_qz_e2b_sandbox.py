import asyncio
import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from typing import ClassVar
from unittest.mock import patch

HARBOR_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = HARBOR_DIR / "qz_e2b_sandbox.py"
sys.path.insert(0, str(HARBOR_DIR))


def install_harbor_stubs() -> None:
    harbor = types.ModuleType("harbor")
    environments = types.ModuleType("harbor.environments")
    capabilities = types.ModuleType("harbor.environments.capabilities")
    e2b = types.ModuleType("harbor.environments.e2b")

    class Capability:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    capabilities.EnvironmentCapabilities = Capability
    capabilities.EnvironmentResourceCapabilities = Capability

    class E2BEnvironment:
        init_calls: ClassVar[list[tuple[tuple, dict]]] = []
        start_calls: ClassVar[list[bool]] = []
        exist_calls: ClassVar[list[str]] = []

        def __init__(self, *args, **kwargs):
            type(self).init_calls.append((args, kwargs))
            self._template_name = "hello-world__abc.123"

        async def start(self, force_build: bool) -> None:
            type(self).start_calls.append(force_build)

        async def _does_template_exist(self) -> bool:
            type(self).exist_calls.append(self._template_name)
            return False

    e2b.E2BEnvironment = E2BEnvironment
    sys.modules.update(
        {
            "harbor": harbor,
            "harbor.environments": environments,
            "harbor.environments.capabilities": capabilities,
            "harbor.environments.e2b": e2b,
        }
    )


def load_module():
    install_harbor_stubs()
    spec = importlib.util.spec_from_file_location("qz_e2b_sandbox", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


QZ_VARS = (
    "QZ_SANDBOX_API_KEY",
    "QZ_SANDBOX_API_URL",
    "SBX_API_KEY",
    "SBX_API_URL",
    "E2B_API_KEY",
    "E2B_API_URL",
    "E2B_VALIDATE_API_KEY",
)


class ApplyQzEnvironmentTest(unittest.TestCase):
    def setUp(self):
        self.module = load_module()

    def run_mapping(self, env: dict[str, str]) -> dict[str, str]:
        cleaned = {name: "" for name in QZ_VARS}
        cleaned.update(env)
        with patch.dict(os.environ, cleaned, clear=False):
            for name in QZ_VARS:
                if not cleaned.get(name):
                    os.environ.pop(name, None)
            self.module.apply_qz_environment()
            return {name: os.environ.get(name, "") for name in QZ_VARS}

    def test_sbx_values_map_to_e2b_with_v1_suffix(self):
        result = self.run_mapping(
            {
                "SBX_API_KEY": "sbx_secret",
                "SBX_API_URL": "https://qz-sbx-api.sii.edu.cn",
            }
        )
        self.assertEqual(result["E2B_API_KEY"], "sbx_secret")
        self.assertEqual(result["E2B_API_URL"], "https://qz-sbx-api.sii.edu.cn/v1")
        self.assertEqual(result["E2B_VALIDATE_API_KEY"], "false")

    def test_defaults_apply_without_any_url(self):
        result = self.run_mapping({"SBX_API_KEY": "sbx_secret"})
        self.assertEqual(result["E2B_API_URL"], "https://qz-sbx-api.sii.edu.cn/v1")

    def test_url_with_existing_v1_suffix_is_not_doubled(self):
        result = self.run_mapping(
            {
                "SBX_API_KEY": "sbx_secret",
                "SBX_API_URL": "https://qz-sbx-api.sii.edu.cn/v1/",
            }
        )
        self.assertEqual(result["E2B_API_URL"], "https://qz-sbx-api.sii.edu.cn/v1")

    def test_qz_specific_variables_win_over_sbx(self):
        result = self.run_mapping(
            {
                "QZ_SANDBOX_API_KEY": "sbx_qz",
                "SBX_API_KEY": "sbx_other",
                "QZ_SANDBOX_API_URL": "https://alt.example.com",
                "SBX_API_URL": "https://qz-sbx-api.sii.edu.cn",
            }
        )
        self.assertEqual(result["E2B_API_KEY"], "sbx_qz")
        self.assertEqual(result["E2B_API_URL"], "https://alt.example.com/v1")

    def test_qz_values_override_ambient_cloud_e2b_settings(self):
        # On a mixed rollout host the ambient E2B_* variables belong to the
        # cloud-E2B backend; a qz process must not send its requests there.
        result = self.run_mapping(
            {
                "SBX_API_KEY": "sbx_secret",
                "SBX_API_URL": "https://qz-sbx-api.sii.edu.cn",
                "E2B_API_KEY": "e2b_cloud_key",
                "E2B_API_URL": "https://api.e2b.app",
                "E2B_VALIDATE_API_KEY": "true",
            }
        )
        self.assertEqual(result["E2B_API_KEY"], "sbx_secret")
        self.assertEqual(result["E2B_API_URL"], "https://qz-sbx-api.sii.edu.cn/v1")
        self.assertEqual(result["E2B_VALIDATE_API_KEY"], "false")

    def test_e2b_key_serves_as_fallback_without_qz_key(self):
        result = self.run_mapping({"E2B_API_KEY": "e2b_direct"})
        self.assertEqual(result["E2B_API_KEY"], "e2b_direct")
        self.assertEqual(result["E2B_API_URL"], "https://qz-sbx-api.sii.edu.cn/v1")

    def test_empty_exported_placeholders_count_as_unset(self):
        # env.sh exports empty placeholders so worker panes inherit the names.
        cleaned = {name: "" for name in QZ_VARS}
        cleaned["SBX_API_KEY"] = "sbx_secret"
        with patch.dict(os.environ, cleaned, clear=False):
            self.module.apply_qz_environment()
            self.assertEqual(os.environ["E2B_API_KEY"], "sbx_secret")
            self.assertEqual(
                os.environ["E2B_API_URL"], "https://qz-sbx-api.sii.edu.cn/v1"
            )
            self.assertEqual(os.environ["E2B_VALIDATE_API_KEY"], "false")


def install_e2b_stub():
    e2b_pkg = types.ModuleType("e2b")
    cc_mod = types.ModuleType("e2b.connection_config")

    class ConnectionConfig:
        domain = "fallback.example.com"

        def get_host(self, sandbox_id, sandbox_domain, port):
            return f"{port}-{sandbox_id}.{sandbox_domain}"

    cc_mod.ConnectionConfig = ConnectionConfig
    sys.modules["e2b"] = e2b_pkg
    sys.modules["e2b.connection_config"] = cc_mod
    return ConnectionConfig


class PatchEnvdHostTest(unittest.TestCase):
    def setUp(self):
        self.module = load_module()
        self.cc_cls = install_e2b_stub()

    def host(self):
        return self.cc_cls().get_host("sbx123", "openapi-qb-nat.sii.edu.cn", 49983)

    def test_patch_adds_sbx_prefix(self):
        self.module.patch_envd_host()
        self.assertEqual(self.host(), "sbx-49983-sbx123.openapi-qb-nat.sii.edu.cn")

    def test_prefix_override_via_environment(self):
        self.module.patch_envd_host()
        with patch.dict(os.environ, {"QZ_SANDBOX_HOST_PREFIX": "alt-"}, clear=False):
            self.assertEqual(self.host(), "alt-49983-sbx123.openapi-qb-nat.sii.edu.cn")

    def test_patch_is_idempotent(self):
        self.module.patch_envd_host()
        first = self.cc_cls.get_host
        self.module.patch_envd_host()
        self.assertIs(self.cc_cls.get_host, first)

    def test_empty_sandbox_domain_falls_back_to_config_domain(self):
        self.module.patch_envd_host()
        result = self.cc_cls().get_host("sbx123", "", 49983)
        self.assertEqual(result, "sbx-49983-sbx123.fallback.example.com")

    def test_missing_e2b_extra_is_a_noop(self):
        sys.modules.pop("e2b.connection_config", None)
        sys.modules.pop("e2b", None)
        self.module.patch_envd_host()  # must not raise


class PreflightTest(unittest.TestCase):
    def setUp(self):
        self.module = load_module()

    def test_preflight_without_key_exits(self):
        cleaned = {name: "" for name in QZ_VARS}
        with patch.dict(os.environ, cleaned, clear=False):
            for name in QZ_VARS:
                os.environ.pop(name, None)
            with self.assertRaises(SystemExit):
                self.module.QzSandboxEnvironment.preflight()

    def test_preflight_with_sbx_key_passes(self):
        cleaned = {name: "" for name in QZ_VARS}
        cleaned["SBX_API_KEY"] = "sbx_secret"
        with patch.dict(os.environ, cleaned, clear=False):
            self.module.QzSandboxEnvironment.preflight()
            self.assertEqual(os.environ["E2B_API_KEY"], "sbx_secret")

    def test_init_applies_mapping_before_super(self):
        cleaned = {name: "" for name in QZ_VARS}
        cleaned["SBX_API_KEY"] = "sbx_secret"
        with patch.dict(os.environ, cleaned, clear=False):
            for name in QZ_VARS:
                if not cleaned.get(name):
                    os.environ.pop(name, None)
            self.module.QzSandboxEnvironment()
            self.assertEqual(os.environ["E2B_API_KEY"], "sbx_secret")


class TemplateResolutionTest(unittest.TestCase):
    def setUp(self):
        self.module = load_module()
        self.env_vars = dict.fromkeys((*QZ_VARS, "QZ_SANDBOX_TEMPLATE"), "")
        self.env_vars["SBX_API_KEY"] = "sbx_secret"

    def make_env(self, **kwargs):
        with patch.dict(os.environ, self.env_vars, clear=False):
            for name, value in self.env_vars.items():
                if not value:
                    os.environ.pop(name, None)
            return self.module.QzSandboxEnvironment(**kwargs)

    def test_sanitize_template_name(self):
        self.assertEqual(
            self.module.sanitize_template_name("hello-world__abc.123/x"),
            "hello_world__abc_123_x",
        )

    def test_auto_template_name_is_sanitized(self):
        env = self.make_env()
        self.assertEqual(env._template_name, "hello_world__abc_123")

    def test_template_kwarg_wins(self):
        env = self.make_env(template="agent_fleet_probe")
        self.assertEqual(env._template_name, "agent_fleet_probe")

    def test_template_env_override(self):
        self.env_vars["QZ_SANDBOX_TEMPLATE"] = "agent_fleet_probe"
        env = self.make_env()
        self.assertEqual(env._template_name, "agent_fleet_probe")

    def test_start_rejects_force_build(self):
        env = self.make_env()
        with self.assertRaises(RuntimeError):
            asyncio.run(env.start(True))

    def test_start_passes_through_without_force_build(self):
        env = self.make_env()
        env.start_calls.clear()
        asyncio.run(env.start(False))
        self.assertEqual(env.start_calls, [False])

    def test_capabilities_advertise_only_verified_behavior(self):
        env = self.make_env()
        caps = env.capabilities
        self.assertFalse(caps.__dict__.get("disable_internet"))
        self.assertFalse(caps.__dict__.get("gpus"))
        resource = self.module.QzSandboxEnvironment.resource_capabilities()
        self.assertEqual(resource.__dict__, {})

    def test_create_template_raises(self):
        env = self.make_env()
        with self.assertRaises(RuntimeError):
            asyncio.run(env._create_template())

    def test_timeout_default_and_valid_values(self):
        with patch.dict(os.environ, {"QZ_SANDBOX_TIMEOUT_SEC": ""}, clear=False):
            self.assertEqual(self.module.qz_sandbox_timeout_sec(), 14400)
        with patch.dict(os.environ, {"QZ_SANDBOX_TIMEOUT_SEC": "600"}, clear=False):
            self.assertEqual(self.module.qz_sandbox_timeout_sec(), 600)

    def test_timeout_rejects_bad_values(self):
        for bad in ("abc", "0", "-5", "14401"):
            with (
                patch.dict(os.environ, {"QZ_SANDBOX_TIMEOUT_SEC": bad}, clear=False),
                self.assertRaises(ValueError),
            ):
                self.module.qz_sandbox_timeout_sec()

    def test_preflight_rejects_bad_timeout(self):
        self.env_vars["QZ_SANDBOX_TIMEOUT_SEC"] = "not-a-number"
        with (
            patch.dict(os.environ, self.env_vars, clear=False),
            self.assertRaises(SystemExit),
        ):
            self.module.QzSandboxEnvironment.preflight()

    def test_override_skips_alias_precheck(self):
        # An override may be a template ID, invisible to the alias lookup;
        # creation is the authority, so the pre-check must pass it through.
        env = self.make_env(template="erbkewn6i1y4zf41mpz8")
        env.exist_calls.clear()
        self.assertTrue(asyncio.run(env._does_template_exist()))
        self.assertEqual(env.exist_calls, [])

    def test_auto_alias_still_prechecked(self):
        env = self.make_env()
        env.exist_calls.clear()
        self.assertFalse(asyncio.run(env._does_template_exist()))
        self.assertEqual(env.exist_calls, ["hello_world__abc_123"])


if __name__ == "__main__":
    unittest.main()
