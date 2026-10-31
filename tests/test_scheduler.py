import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

import scheduler


ROOT = Path(__file__).resolve().parents[1]
SCHEDULER_PATH = ROOT / "scheduler.py"
HEADER = ("task_id", "duration", "priority", "dependencies")
HEADER_TEXT = ",".join(HEADER) + "\n"
SAMPLES = (
    ("basic", 2),
    ("simultaneous", 2),
    ("idle-and-ties", 3),
    ("empty", 2),
    ("unknown-dependency", 2),
    ("cycle", 2),
    ("duplicate-id", 2),
)


def run_cli(input_path, workers):
    return subprocess.run(
        [
            sys.executable,
            str(SCHEDULER_PATH),
            "--input",
            str(input_path),
            "--workers",
            str(workers),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def write_csv(tmp_path, rows, *, bom=False, crlf=False):
    path = tmp_path / "tasks.csv"
    with path.open("w", encoding="utf-8-sig" if bom else "utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\r\n" if crlf else "\n")
        writer.writerow(HEADER)
        writer.writerows(rows)
    return path


def parse_tasks(tmp_path, rows):
    return scheduler.load_tasks(write_csv(tmp_path, rows))


def error_code(result):
    payload = json.loads(result.stdout)
    assert payload["status"] == "error"
    assert "schedule" not in payload
    assert payload["errors"]
    assert payload["errors"][0]["message"]
    return payload["errors"][0]["code"], payload


def assert_real_cycle(cycle, dependency_map):
    assert len(cycle) >= 2
    assert cycle[0] == cycle[-1]
    for source, target in zip(cycle, cycle[1:]):
        assert target in dependency_map[source]


@pytest.mark.parametrize(("name", "workers"), SAMPLES)
def test_all_supplied_inputs_match_expected(name, workers):
    input_path = ROOT / "inputs" / f"{name}.csv"
    expected_path = ROOT / "expected" / f"{name}.json"
    result = run_cli(input_path, workers)
    actual = json.loads(result.stdout)
    expected = json.loads(expected_path.read_text(encoding="utf-8"))

    if expected["status"] == "ok":
        assert result.returncode == 0
        assert actual == expected
    else:
        assert result.returncode != 0
        assert actual["status"] == "error"
        assert actual["errors"][0]["code"] == expected["errors"][0]["code"]
        assert "schedule" not in actual
        if expected["errors"][0]["code"] == scheduler.CYCLE_DETECTED:
            tasks = scheduler.load_tasks(input_path)
            dependencies = {
                task.task_id: set(task.dependencies) for task in tasks
            }
            assert_real_cycle(actual["errors"][0]["cycle"], dependencies)


def test_priority_and_ascii_ties_ignore_input_order(tmp_path):
    rows = [
        ("j2", 1, 0, ""),
        ("J2", 1, 0, ""),
        ("a", 1, 0, ""),
        ("J10", 1, 0, ""),
        ("A", 1, 0, ""),
    ]
    path = write_csv(tmp_path, rows)

    for order in (rows, list(reversed(rows))):
        path = write_csv(tmp_path, order)
        tasks = scheduler.load_tasks(path)
        entries, _ = scheduler.schedule_tasks(tasks, workers=1)
        assert [entry["task_id"] for entry in entries] == [
            "A",
            "J10",
            "J2",
            "a",
            "j2",
        ]


def test_multiple_dependencies_and_forward_references(tmp_path):
    tasks = parse_tasks(
        tmp_path,
        [
            ("Join", 1, 0, "Alpha,Beta"),
            ("Beta", 2, 0, ""),
            ("Alpha", 2, 1, ""),
        ],
    )
    entries, makespan = scheduler.schedule_tasks(tasks, workers=2)
    by_id = {entry["task_id"]: entry for entry in entries}

    assert by_id["Alpha"]["start"] == 0
    assert by_id["Beta"]["start"] == 0
    assert by_id["Join"]["start"] == 2
    assert makespan == 3


def test_all_simultaneous_completions_are_processed_before_dispatch(tmp_path):
    tasks = parse_tasks(
        tmp_path,
        [
            ("A", 2, 0, ""),
            ("B", 2, 1, ""),
            ("C", 1, 0, "A,B"),
            ("D", 1, 1, "A"),
        ],
    )
    entries, _ = scheduler.schedule_tasks(tasks, workers=2)
    starts_at_two = [
        (entry["task_id"], entry["worker_id"])
        for entry in entries
        if entry["start"] == 2
    ]
    assert starts_at_two == [("C", 1), ("D", 2)]


def test_lowest_worker_idle_since_earlier_time_is_used(tmp_path):
    tasks = parse_tasks(
        tmp_path,
        [
            ("A", 1, 0, ""),
            ("B", 5, 0, ""),
            ("C", 1, 0, "A,B"),
        ],
    )
    entries, _ = scheduler.schedule_tasks(tasks, workers=2)
    task_c = next(entry for entry in entries if entry["task_id"] == "C")
    assert (task_c["worker_id"], task_c["start"]) == (1, 5)


def test_idle_gap_and_million_unit_duration_jump(tmp_path):
    tasks = parse_tasks(
        tmp_path,
        [
            ("A", 1_000_000, 0, ""),
            ("X", 1, 0, ""),
            ("D", 1, 0, "A,X"),
        ],
    )
    entries, makespan = scheduler.schedule_tasks(tasks, workers=2)
    task_d = next(entry for entry in entries if entry["task_id"] == "D")
    assert (task_d["worker_id"], task_d["start"], task_d["end"]) == (
        1,
        1_000_000,
        1_000_001,
    )
    assert makespan == 1_000_001


@pytest.mark.parametrize(
    ("rows", "code"),
    [
        ([("A", 1, 0, "Missing")], scheduler.INVALID_DEPENDENCY),
        ([("A", 1, 0, "A")], scheduler.INVALID_DEPENDENCY),
        ([("A", 1, 0, "B,B"), ("B", 1, 0, "")], scheduler.INVALID_DEPENDENCY),
        (
            [("A", 1, 0, ""), ("B", 1, 0, ""), ("C", 1, 0, "A,,B")],
            scheduler.INVALID_DEPENDENCY,
        ),
        ([("A", 1, 0, "bad.id")], scheduler.INVALID_DEPENDENCY),
    ],
)
def test_unknown_self_and_repeated_dependencies(tmp_path, rows, code):
    result = run_cli(write_csv(tmp_path, rows), 2)
    actual_code, _ = error_code(result)
    assert result.returncode != 0
    assert actual_code == code


def test_cycle_with_unrelated_tasks_has_real_closed_witness(tmp_path):
    path = write_csv(
        tmp_path,
        [
            ("A", 1, 0, "B"),
            ("B", 1, 0, "C"),
            ("C", 1, 0, "A"),
            ("Independent", 1, 0, ""),
        ],
    )
    result = run_cli(path, 2)
    code, payload = error_code(result)
    assert result.returncode != 0
    assert code == scheduler.CYCLE_DETECTED
    assert_real_cycle(
        payload["errors"][0]["cycle"],
        {"A": {"B"}, "B": {"C"}, "C": {"A"}, "Independent": set()},
    )


@pytest.mark.parametrize(
    ("contents", "code"),
    [
        ("wrong,header\nA,1,0,\n", scheduler.INVALID_CSV),
        ("task_id,duration,priority,dependencies\nA,1,0\n", scheduler.INVALID_CSV),
        ("task_id,duration,priority,dependencies\n1bad,1,0,\n", scheduler.INVALID_TASK),
        ("task_id,duration,priority,dependencies\nA,0,0,\n", scheduler.INVALID_TASK),
        ("task_id,duration,priority,dependencies\nA,1,1.5,\n", scheduler.INVALID_TASK),
        ("task_id,duration,priority,dependencies\nA,1,0,\nA,2,0,\n", scheduler.DUPLICATE_TASK),
    ],
)
def test_invalid_csv_and_task_inputs(tmp_path, contents, code):
    path = tmp_path / "invalid.csv"
    path.write_text(contents, encoding="utf-8", newline="")
    result = run_cli(path, 2)
    actual_code, _ = error_code(result)
    assert result.returncode != 0
    assert actual_code == code


def test_malformed_csv_is_invalid_csv(tmp_path):
    path = tmp_path / "malformed.csv"
    path.write_text(
        'task_id,duration,priority,dependencies\nA,1,0,"unterminated\n',
        encoding="utf-8",
        newline="",
    )
    result = run_cli(path, 2)
    code, _ = error_code(result)
    assert result.returncode != 0
    assert code == scheduler.INVALID_CSV


def test_invalid_utf8_is_invalid_csv(tmp_path):
    path = tmp_path / "invalid-encoding.csv"
    path.write_bytes(b"task_id,duration,priority,dependencies\nA,1,0,\xff\n")
    result = run_cli(path, 2)
    code, _ = error_code(result)
    assert result.returncode != 0
    assert code == scheduler.INVALID_CSV
    assert result.stderr == ""


def test_unreadable_input_is_read_error(tmp_path):
    result = run_cli(tmp_path / "does-not-exist.csv", 2)
    code, _ = error_code(result)
    assert result.returncode != 0
    assert code == scheduler.READ_ERROR


@pytest.mark.parametrize("workers", ["0", "33", "not-a-number"])
def test_invalid_worker_counts(workers, tmp_path):
    path = write_csv(tmp_path, [])
    result = subprocess.run(
        [
            sys.executable,
            str(SCHEDULER_PATH),
            "--input",
            str(path),
            "--workers",
            workers,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    code, _ = error_code(result)
    assert result.returncode != 0
    assert code == scheduler.INVALID_ARGUMENT


def test_5000_digit_worker_count_returns_json_error(tmp_path):
    path = write_csv(tmp_path, [])
    result = run_cli(path, "9" * 5000)
    code, _ = error_code(result)
    assert result.returncode == 1
    assert code == scheduler.INVALID_ARGUMENT
    assert result.stderr == ""


def test_5000_digit_duration_returns_json_error(tmp_path):
    path = tmp_path / "huge-duration.csv"
    path.write_text(
        HEADER_TEXT + f"A,{'9' * 5000},0,\n",
        encoding="utf-8",
        newline="",
    )
    result = run_cli(path, 2)
    code, _ = error_code(result)
    assert result.returncode == 1
    assert code == scheduler.INVALID_TASK
    assert result.stderr == ""


def test_2001_tasks_exceeds_task_limit(tmp_path):
    rows = [(f"T{index:04}", 1, 0, "") for index in range(2001)]
    result = run_cli(write_csv(tmp_path, rows), 2)
    code, _ = error_code(result)
    assert result.returncode != 0
    assert code == scheduler.INVALID_TASK


def test_header_only_input_is_empty_schedule(tmp_path):
    path = write_csv(tmp_path, [])
    result = run_cli(path, 2)
    assert result.returncode == 0
    assert json.loads(result.stdout) == {
        "status": "ok",
        "workers": 2,
        "makespan": 0,
        "schedule": [],
    }


def test_bom_and_crlf_are_supported(tmp_path):
    path = write_csv(tmp_path, [("A", 3, 0, "")], bom=True, crlf=True)
    result = run_cli(path, 2)
    assert result.returncode == 0
    assert json.loads(result.stdout)["schedule"] == [
        {"task_id": "A", "worker_id": 1, "start": 0, "end": 3}
    ]


def test_2000_task_chain_runs_through_core_functions(tmp_path):
    task_count = 2000
    rows = [
        (f"T{index:04}", 1, 0, "" if index == 0 else f"T{index - 1:04}")
        for index in range(task_count)
    ]
    tasks = parse_tasks(tmp_path, rows)
    assert scheduler.find_cycle(tasks) is None

    entries, makespan = scheduler.schedule_tasks(tasks, workers=1)
    assert len(entries) == task_count
    assert makespan == task_count
    assert entries[0] == {
        "task_id": "T0000",
        "worker_id": 1,
        "start": 0,
        "end": 1,
    }
    assert entries[-1] == {
        "task_id": "T1999",
        "worker_id": 1,
        "start": task_count - 1,
        "end": task_count,
    }
