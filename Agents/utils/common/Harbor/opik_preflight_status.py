"""Record known Opik preflight failures for final benchmark summaries."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

FAILURE_FILENAME = "opik-preflight-failed.json"


def write_failure(root: Path, reason: str, task_id: str = "") -> Path:
    """Atomically record one known preflight failure without connection data."""
    root.mkdir(parents=True, exist_ok=True)
    destination = root / FAILURE_FILENAME
    temporary = destination.with_name(f".{destination.name}.tmp.{os.getpid()}")
    temporary.write_text(
        json.dumps(
            {"reason": reason, "task_id": task_id},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, destination)
    return destination


def read_failures(root: Path) -> list[tuple[str, str]]:
    """Read direct-run and worker failure markers without scanning trial artifacts."""
    paths: list[Path] = []
    direct_failure = root / FAILURE_FILENAME
    if direct_failure.is_file():
        paths.append(direct_failure)
    if root.is_dir():
        paths.extend(root.glob(f"worker-*/*/{FAILURE_FILENAME}"))

    failures: list[tuple[str, str]] = []
    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        fallback_task_id = (
            path.parent.name
            if path.parent.parent.name.startswith("worker-")
            else "<direct-run>"
        )
        task_id = str(payload.get("task_id") or fallback_task_id)
        reason = str(payload.get("reason") or "unspecified")
        failures.append((task_id, reason))
    return sorted(failures)


def summary_lines(root: Path, tracing_enabled: bool) -> list[str]:
    """Report known failure or explicitly leave trace persistence unverified."""
    failures = read_failures(root)
    if failures:
        lines = [
            f"Opik preflight failures: {len(failures)}",
            "Trace delivery: unavailable for the tasks listed below",
            *[f"  - {task}: {reason}" for task, reason in failures],
        ]
    elif tracing_enabled:
        lines = [
            "Opik preflight: no failure recorded",
            "Trace delivery: unverified; persistence in Opik was not checked",
        ]
    else:
        lines = ["Opik tracing: disabled"]
    lines.append("Benchmark result: Harbor result artifacts remain authoritative")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    record_parser = subparsers.add_parser("record-failure")
    record_parser.add_argument("root", type=Path)
    record_parser.add_argument("--reason", required=True)
    record_parser.add_argument("--task-id", default="")

    summary_parser = subparsers.add_parser("summary")
    summary_parser.add_argument("root", type=Path)
    summary_parser.add_argument("--tracing-enabled", action="store_true")

    args = parser.parse_args()
    if args.command == "record-failure":
        write_failure(args.root, args.reason, args.task_id)
        return 0
    print("\n".join(summary_lines(args.root, args.tracing_enabled)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
