from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from Agents.utils.common.Harbor.opik_preflight_status import (
    FAILURE_FILENAME,
    read_failures,
    summary_lines,
    write_failure,
)


class OpikPreflightStatusTest(unittest.TestCase):
    def test_failure_marker_records_only_task_and_reason(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            os.environ,
            {
                "OPIK_API_KEY": "secret-opik-key",
                "OPIK_URL": "https://user:password@opik.example/api",
            },
        ):
            path = write_failure(Path(temporary), "health_check_failed", "task-a")
            content = path.read_text(encoding="utf-8")
            payload = json.loads(content)

        self.assertEqual(
            payload,
            {"reason": "health_check_failed", "task_id": "task-a"},
        )
        self.assertNotIn("secret-opik-key", content)
        self.assertNotIn("password", content)
        self.assertNotIn("opik.example", content)

    def test_reads_only_direct_and_worker_failure_markers(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_failure(root / "worker-1" / "1-task-a", "health_check_failed")
            write_failure(
                root / "worker-2" / "2-task-b",
                "ingestion_check_failed",
                "task-b",
            )
            deep_marker = root / "trial" / "artifact" / "nested" / FAILURE_FILENAME
            deep_marker.parent.mkdir(parents=True)
            deep_marker.write_text('{}\n', encoding="utf-8")

            failures = read_failures(root)

        self.assertEqual(
            failures,
            [
                ("1-task-a", "health_check_failed"),
                ("task-b", "ingestion_check_failed"),
            ],
        )

    def test_failed_summary_lists_tasks_and_preserves_benchmark_meaning(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_failure(
                root / "worker-1" / "1-task-a",
                "health_check_failed",
                "task-a",
            )

            summary = "\n".join(summary_lines(root, tracing_enabled=True))

        self.assertIn("Opik preflight failures: 1", summary)
        self.assertIn("Trace delivery: unavailable", summary)
        self.assertIn("  - task-a: health_check_failed", summary)
        self.assertIn("Benchmark result: Harbor result artifacts remain authoritative", summary)

    def test_no_failure_does_not_claim_trace_delivery(self):
        with tempfile.TemporaryDirectory() as temporary:
            summary = "\n".join(
                summary_lines(Path(temporary), tracing_enabled=True)
            )

        self.assertIn("Opik preflight: no failure recorded", summary)
        self.assertIn("Trace delivery: unverified", summary)

    def test_disabled_tracing_is_reported_without_status_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            summary = "\n".join(
                summary_lines(Path(temporary), tracing_enabled=False)
            )

        self.assertIn("Opik tracing: disabled", summary)


if __name__ == "__main__":
    unittest.main()
