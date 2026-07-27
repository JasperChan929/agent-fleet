import os
import subprocess
import tempfile
import unittest
from pathlib import Path


HARBOR_DIR = Path(__file__).resolve().parents[1]
ENV_SH = HARBOR_DIR / "env.sh"


class HarborTaskSelectionTest(unittest.TestCase):
    def run_env_function(
        self,
        command: str,
        *,
        overrides: dict[str, str],
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.update(overrides)
        return subprocess.run(
            ["bash", "-c", f'. "$1"; {command}', "bash", str(ENV_SH)],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_registry_selection_is_exact_and_sets_include_tasks(self) -> None:
        result = self.run_env_function(
            (
                "harbor_prepare_registry_task_selection; "
                'printf "include=%s\\ntb_include=%s\\n" '
                '"$INCLUDE_TASKS" "$TB_INCLUDE_TASKS"'
            ),
            overrides={
                "DATASET_NAME": "terminalbench21",
                "FLEET_TASKS": "fix-git,break-filter-js-from-html",
                "TRACE_TO_OPIK": "false",
            },
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("include=fix-git,break-filter-js-from-html", result.stdout)
        self.assertIn("tb_include=fix-git,break-filter-js-from-html", result.stdout)

    def test_registry_selection_reports_every_missing_task(self) -> None:
        result = self.run_env_function(
            "harbor_prepare_registry_task_selection",
            overrides={
                "DATASET_NAME": "sweverify",
                "FLEET_TASKS": "missing-a,astropy__astropy-12907,missing-b",
                "TRACE_TO_OPIK": "false",
            },
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("unknown task(s): missing-a, missing-b", result.stderr)

    def test_local_selection_filters_and_guards_run_reuse(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dataset = root / "dataset"
            output = root / "run"
            for task_id in ("task-a", "task-b", "task-c"):
                task_dir = dataset / task_id
                task_dir.mkdir(parents=True)
                (task_dir / "task.yaml").write_text("version: 1\n", encoding="utf-8")

            common = {
                "DATASET_NAME": "auto",
                "DATASET_PATH": str(dataset),
                "OUTPUT_PATH": str(output),
                "TASK_FILE": str(output / "tasks.txt"),
                "QUEUE_DIR": str(output / "queue"),
                "RUNTIME_DIR": str(output / "runtime"),
                "TRACE_TO_OPIK": "false",
            }
            first = self.run_env_function(
                (
                    'mkdir -p "$QUEUE_DIR" "$RUNTIME_DIR"; '
                    "harbor_prepare_task_file"
                ),
                overrides={
                    **common,
                    "FLEET_TASKS": "task-c,task-a",
                },
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(
                (output / "tasks.txt").read_text(encoding="utf-8"),
                "task-c\ntask-a\n",
            )

            same = self.run_env_function(
                (
                    'mkdir -p "$QUEUE_DIR" "$RUNTIME_DIR"; '
                    "harbor_prepare_task_file"
                ),
                overrides={
                    **common,
                    "FLEET_TASKS": "task-c,task-a",
                },
            )
            self.assertEqual(same.returncode, 0, same.stderr)

            mismatch = self.run_env_function(
                (
                    'mkdir -p "$QUEUE_DIR" "$RUNTIME_DIR"; '
                    "harbor_prepare_task_file"
                ),
                overrides={
                    **common,
                    "FLEET_TASKS": "task-b",
                },
            )
            self.assertEqual(mismatch.returncode, 2)
            self.assertIn("RESET_RUN=1", mismatch.stderr)
            self.assertEqual(
                (output / "tasks.txt").read_text(encoding="utf-8"),
                "task-c\ntask-a\n",
            )

            reset = self.run_env_function(
                (
                    'mkdir -p "$QUEUE_DIR" "$RUNTIME_DIR"; '
                    "harbor_prepare_task_file"
                ),
                overrides={
                    **common,
                    "FLEET_TASKS": "task-b",
                    "RESET_RUN": "1",
                },
            )
            self.assertEqual(reset.returncode, 0, reset.stderr)
            self.assertEqual(
                (output / "tasks.txt").read_text(encoding="utf-8"),
                "task-b\n",
            )

    def test_local_selection_reports_every_missing_task_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dataset = root / "dataset"
            output = root / "run"
            task_dir = dataset / "task-a"
            task_dir.mkdir(parents=True)
            (task_dir / "task.yaml").write_text("version: 1\n", encoding="utf-8")

            result = self.run_env_function(
                (
                    'mkdir -p "$QUEUE_DIR" "$RUNTIME_DIR"; '
                    "harbor_prepare_task_file"
                ),
                overrides={
                    "DATASET_NAME": "auto",
                    "DATASET_PATH": str(dataset),
                    "OUTPUT_PATH": str(output),
                    "TASK_FILE": str(output / "tasks.txt"),
                    "QUEUE_DIR": str(output / "queue"),
                    "RUNTIME_DIR": str(output / "runtime"),
                    "FLEET_TASKS": "missing-a,task-a,missing-b",
                    "TRACE_TO_OPIK": "false",
                },
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("unknown task(s): missing-a, missing-b", result.stderr)
            self.assertFalse((output / "tasks.txt").exists())


if __name__ == "__main__":
    unittest.main()
