"""qz variant of Harbor's Pi agent, for direct `harbor run` use:

    harbor run -a qz_pi_agent:QzPi -m <model> \
      --ak base_url=<gateway-url> --ak api_key=<gateway-key> ...

Two deltas against the stock agent, both forced by qz sandbox egress rules
(domestic-only internet, no github/nodejs.org/npmjs):

- install node + pi from npmmirror instead of nvm/github;
- talk to the SII model gateway through a custom pi provider (models.json in
  PI_CODING_AGENT_DIR), contract copied from scripts/pi_prompt.py.
"""

from __future__ import annotations

import json
import os
import shlex
from typing import override

from harbor.agents.installed.base import with_prompt_template
from harbor.agents.installed.pi import Pi
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

NODE_VERSION = "v22.14.0"
NODE_URL = (
    "https://registry.npmmirror.com/-/binary/node/"
    f"{NODE_VERSION}/node-{NODE_VERSION}-linux-x64.tar.gz"
)
NPM_REGISTRY = "https://registry.npmmirror.com"
PROVIDER = "qzgw"
API_KEY_ENV = "QZ_GW_API_KEY"
AGENT_DIR = "/tmp/pi-agent-dir"


class QzPi(Pi):
    def __init__(self, *args, base_url: str = "", api_key: str = "", **kwargs):
        super().__init__(*args, **kwargs)
        url = (base_url or os.environ.get("BASE_URL", "")).strip().rstrip("/")
        if url and not url.endswith("/v1"):
            url = f"{url}/v1"
        self._qz_base_url = url
        self._qz_api_key = (api_key or os.environ.get("API_KEY", "")).strip()
        if not self._qz_base_url or not self._qz_api_key:
            raise ValueError("QzPi requires base_url and api_key agent kwargs")

    @override
    def get_version_command(self) -> str | None:
        return "pi --version"

    @override
    async def install(self, environment: BaseEnvironment) -> None:
        version_spec = f"@{self._version}" if self._version else "@latest"
        await self.exec_as_root(
            environment,
            command=(
                "set -euo pipefail; "
                f"curl -fsSL {NODE_URL} -o /tmp/node.tgz && "
                "mkdir -p /usr/local/node && "
                "tar -xzf /tmp/node.tgz -C /usr/local/node --strip-components=1 && "
                "ln -sf /usr/local/node/bin/node /usr/local/bin/node && "
                "ln -sf /usr/local/node/bin/npm /usr/local/bin/npm && "
                f"npm install -g --registry {NPM_REGISTRY} "
                f"@mariozechner/pi-coding-agent{version_spec} && "
                "ln -sf /usr/local/node/bin/pi /usr/local/bin/pi && "
                "pi --version"
            ),
        )

    def _models_config(self) -> dict:
        # Provider contract mirrors scripts/pi_prompt.py (SII gateway / GLM).
        return {
            "providers": {
                PROVIDER: {
                    "baseUrl": self._qz_base_url,
                    "api": "openai-completions",
                    # Literal value: this pi build did not resolve a "$VAR"
                    # reference here (gateway saw a bad key). The file lives
                    # inside the throwaway sandbox only.
                    "apiKey": self._qz_api_key,
                    "compat": {
                        "supportsDeveloperRole": False,
                        "supportsReasoningEffort": False,
                        "supportsUsageInStreaming": True,
                        "maxTokensField": "max_tokens",
                        "thinkingFormat": "zai",
                    },
                    "models": [
                        {
                            "id": self.model_name,
                            "name": "qz smoke model",
                            "reasoning": True,
                            "input": ["text"],
                            "contextWindow": 204800,
                            "maxTokens": 32768,
                            "cost": {
                                "input": 0,
                                "output": 0,
                                "cacheRead": 0,
                                "cacheWrite": 0,
                            },
                        }
                    ],
                }
            }
        }

    @with_prompt_template
    @override
    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        if not self.model_name:
            raise ValueError("QzPi requires a model name (-m)")

        models_payload = shlex.quote(
            json.dumps(self._models_config(), separators=(",", ":"))
        )
        await self.exec_as_agent(
            environment,
            command=(
                f"mkdir -p {AGENT_DIR} && "
                f"printf %s {models_payload} > {AGENT_DIR}/models.json"
            ),
        )

        cli_flags = self.build_cli_flags()
        if cli_flags:
            cli_flags += " "
        await self.exec_as_agent(
            environment,
            command=(
                "pi --print --mode json --no-session "
                f"--provider {PROVIDER} --model {shlex.quote(self.model_name)} "
                f"{cli_flags}"
                f"{shlex.quote(instruction)} "
                "2>&1 </dev/null | grep -v '\"type\":\"message_update\"' | "
                f"stdbuf -oL tee /logs/agent/{self._OUTPUT_FILENAME}"
            ),
            env={
                API_KEY_ENV: self._qz_api_key,
                "PI_CODING_AGENT_DIR": AGENT_DIR,
                "PI_OFFLINE": "1",
            },
        )
