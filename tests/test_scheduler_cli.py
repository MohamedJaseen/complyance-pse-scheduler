"""Executable tests for scheduler.py."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCHEDULER = Path(__file__).resolve().parents[1] / "scheduler.py"
HEADER = "task_id,duration,priority,dependencies\n"


class SchedulerCliTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.input_path = Path(self.temp_dir.name) / "tasks.csv"

    def run_scheduler(self, contents, workers=2, raw_bytes=False, path=None):
        input_path = path or self.input_path
        if contents is not None:
            if raw_bytes:
                input_path.write_bytes(contents)
            else:
                with input_path.open("w", encoding="utf-8", newline="") as output:
                    output.write(contents)
        return subprocess.run(
            [
                sys.executable,
                str(SCHEDULER),
                "--input",
                str(input_path),
                "--workers",
                str(workers),
            ],
            capture_output=True,
            text=True,
            check=False,
        )

    def assert_error(self, result, code):
        self.assertNotEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["errors"][0]["code"], code)
        self.assertTrue(payload["errors"][0]["message"])
        self.assertNotIn("schedule", payload)

    def test_priority_and_task_id_ties_ignore_input_order(self):
        result = self.run_scheduler(
            HEADER + "B,1,4,\nJ2,1,2,\nJ10,1,2,\nA,1,4,\n",
            workers=1,
        )
        payload = json.loads(result.stdout)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            [entry["task_id"] for entry in payload["schedule"]],
            ["J10", "J2", "A", "B"],
        )

    def test_forward_reference(self):
        result = self.run_scheduler(HEADER + "B,2,0,A\nA,1,5,\n", workers=1)
        payload = json.loads(result.stdout)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            [(entry["task_id"], entry["start"]) for entry in payload["schedule"]],
            [("A", 0), ("B", 1)],
        )

    def test_multiple_dependencies_and_simultaneous_completions(self):
        result = self.run_scheduler(
            HEADER + "A,2,0,\nB,2,1,\nC,1,0,\"A,B\"\n",
            workers=2,
        )
        payload = json.loads(result.stdout)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            [(entry["task_id"], entry["start"]) for entry in payload["schedule"]],
            [("A", 0), ("B", 0), ("C", 2)],
        )

    def test_uses_worker_idle_since_an_earlier_completion(self):
        result = self.run_scheduler(
            HEADER + "A,1,0,\nB,5,0,\nC,1,0,\"A,B\"\n",
            workers=2,
        )
        payload = json.loads(result.stdout)
        self.assertEqual(result.returncode, 0)
        task_c = next(entry for entry in payload["schedule"] if entry["task_id"] == "C")
        self.assertEqual((task_c["worker_id"], task_c["start"]), (1, 5))

    def test_cycle_with_unrelated_valid_task_has_closed_witness(self):
        result = self.run_scheduler(
            HEADER + "A,1,0,B\nB,1,0,A\nIndependent,2,1,\n"
        )
        self.assert_error(result, "CYCLE_DETECTED")
        cycle = json.loads(result.stdout)["errors"][0]["cycle"]
        self.assertEqual(cycle[0], cycle[-1])
        dependencies = {"A": {"B"}, "B": {"A"}, "Independent": set()}
        for source, target in zip(cycle, cycle[1:]):
            self.assertIn(target, dependencies[source])

    def test_iterative_cycle_detection_handles_a_long_path(self):
        task_count = 1500
        rows = "".join(
            f"T{index},1,0,T{(index + 1) % task_count}\n"
            for index in range(task_count)
        )
        result = self.run_scheduler(HEADER + rows + "Independent,1,0,\n")
        self.assert_error(result, "CYCLE_DETECTED")
        cycle = json.loads(result.stdout)["errors"][0]["cycle"]
        self.assertEqual(len(cycle), task_count + 1)
        self.assertEqual(cycle[0], cycle[-1])

    def test_header_only_csv(self):
        result = self.run_scheduler(HEADER, workers=2)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            json.loads(result.stdout),
            {"status": "ok", "workers": 2, "makespan": 0, "schedule": []},
        )

    def test_utf8_bom_and_crlf(self):
        content = b"\xef\xbb\xbftask_id,duration,priority,dependencies\r\nA,2,0,\r\n"
        result = self.run_scheduler(content, raw_bytes=True)
        payload = json.loads(result.stdout)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(payload["schedule"][0]["task_id"], "A")

    def test_32_workers_use_ids_one_through_32(self):
        rows = "".join(f"T{index},1,0,\n" for index in range(32))
        result = self.run_scheduler(HEADER + rows, workers=32)
        payload = json.loads(result.stdout)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            [entry["worker_id"] for entry in payload["schedule"]],
            list(range(1, 33)),
        )

    def test_invalid_argument(self):
        result = self.run_scheduler(HEADER, workers=0)
        self.assert_error(result, "INVALID_ARGUMENT")

    def test_read_error(self):
        missing_path = Path(self.temp_dir.name) / "missing.csv"
        result = self.run_scheduler(None, path=missing_path)
        self.assert_error(result, "READ_ERROR")

    def test_invalid_csv(self):
        result = self.run_scheduler("wrong,header\nA,1,0,\n")
        self.assert_error(result, "INVALID_CSV")

    def test_invalid_task(self):
        result = self.run_scheduler(HEADER + "A,0,0,\n")
        self.assert_error(result, "INVALID_TASK")

    def test_duplicate_task(self):
        result = self.run_scheduler(HEADER + "A,1,0,\nA,2,0,\n")
        self.assert_error(result, "DUPLICATE_TASK")

    def test_invalid_dependency_variants(self):
        for dependency in ("Unknown", "A", '"B,,C"', '"B,B"', "bad.id"):
            with self.subTest(dependency=dependency):
                result = self.run_scheduler(
                    HEADER + f"A,1,0,{dependency}\nB,1,0,\nC,1,0,\n"
                )
                self.assert_error(result, "INVALID_DEPENDENCY")


if __name__ == "__main__":
    unittest.main()
