#!/usr/bin/env python3
"""Dependency-aware virtual-time task scheduler."""

import csv
import heapq
import json
import re
import sys
from dataclasses import dataclass


CSV_HEADER = ("task_id", "duration", "priority", "dependencies")
DEPENDENCY_SEPARATOR = ","

JSON_STATUS_FIELD = "status"
JSON_WORKERS_FIELD = "workers"
JSON_MAKESPAN_FIELD = "makespan"
JSON_SCHEDULE_FIELD = "schedule"
JSON_ERRORS_FIELD = "errors"
JSON_TASK_ID_FIELD = "task_id"
JSON_WORKER_ID_FIELD = "worker_id"
JSON_START_FIELD = "start"
JSON_END_FIELD = "end"
JSON_CODE_FIELD = "code"
JSON_MESSAGE_FIELD = "message"
JSON_CYCLE_FIELD = "cycle"

WORKER_ID_BASE = 1
SUCCESS_EXIT_CODE = 0
ERROR_EXIT_CODE = 1

MAX_WORKERS = 32
MAX_TASKS = 2000
MIN_DURATION = 1
MAX_DURATION = 1_000_000
MIN_PRIORITY = 0
MAX_PRIORITY = 1000
ASCII_WHITESPACE = " \t\n\r\v\f"
TASK_ID_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,31}\Z")

INVALID_ARGUMENT = "INVALID_ARGUMENT"
READ_ERROR = "READ_ERROR"
INVALID_CSV = "INVALID_CSV"
INVALID_TASK = "INVALID_TASK"
DUPLICATE_TASK = "DUPLICATE_TASK"
INVALID_DEPENDENCY = "INVALID_DEPENDENCY"
CYCLE_DETECTED = "CYCLE_DETECTED"


class SchedulerError(Exception):
    def __init__(self, code, message, cycle=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.cycle = cycle


@dataclass(frozen=True)
class Task:
    task_id: str
    duration: int
    priority: int
    dependencies: tuple


def parse_uint(text, minimum, maximum):
    if not text or not text.isascii() or not text.isdigit():
        return None
    digits = text.lstrip("0") or "0"
    if len(digits) > len(str(maximum)):
        return None
    value = int(digits)
    return value if minimum <= value <= maximum else None


def parse_arguments(arguments):
    if len(arguments) != 4:
        raise SchedulerError(
            INVALID_ARGUMENT,
            "Expected exactly --input PATH --workers W.",
        )

    options = {}
    for index in range(0, len(arguments), 2):
        option = arguments[index]
        value = arguments[index + 1]
        if option not in ("--input", "--workers") or option in options:
            raise SchedulerError(
                INVALID_ARGUMENT,
                "Use --input PATH and --workers W exactly once each.",
            )
        options[option] = value

    if "--input" not in options or not options["--input"]:
        raise SchedulerError(INVALID_ARGUMENT, "--input requires a path.")
    worker_text = options.get("--workers", "")
    workers = parse_uint(worker_text, WORKER_ID_BASE, MAX_WORKERS)
    if workers is None:
        raise SchedulerError(
            INVALID_ARGUMENT,
            "--workers must be an unsigned decimal integer from 1 to 32.",
        )
    return options["--input"], workers


def _parse_number(value, field_name, minimum, maximum, task_id):
    number = parse_uint(value, minimum, maximum)
    if number is None:
        raise SchedulerError(
            INVALID_TASK,
            f"Task {task_id!r} {field_name} must be unsigned decimal digits from {minimum} to {maximum}.",
        )
    return number


def load_tasks(input_path):
    tasks = []
    task_ids = set()
    try:
        with open(input_path, "r", encoding="utf-8-sig", newline="") as source:
            reader = csv.reader(source, strict=True)
            header_seen = False

            for record_number, raw_row in enumerate(reader, start=1):
                row = [field.strip(ASCII_WHITESPACE) for field in raw_row]
                if not row or (len(row) == 1 and not row[0]):
                    continue

                if not header_seen:
                    if tuple(row) != CSV_HEADER:
                        raise SchedulerError(
                            INVALID_CSV,
                            "CSV header must be task_id,duration,priority,dependencies in that order.",
                        )
                    header_seen = True
                    continue

                if len(row) != len(CSV_HEADER):
                    raise SchedulerError(
                        INVALID_CSV,
                        f"CSV record {record_number} must contain exactly four fields.",
                    )

                task_id, duration_text, priority_text, dependencies_text = row
                if not TASK_ID_PATTERN.fullmatch(task_id):
                    raise SchedulerError(
                        INVALID_TASK,
                        f"CSV record {record_number} has an invalid task ID.",
                    )
                if task_id in task_ids:
                    raise SchedulerError(
                        DUPLICATE_TASK,
                        f"Task ID {task_id!r} occurs more than once.",
                    )

                duration = _parse_number(
                    duration_text, "duration", MIN_DURATION, MAX_DURATION, task_id
                )
                priority = _parse_number(
                    priority_text, "priority", MIN_PRIORITY, MAX_PRIORITY, task_id
                )
                if len(tasks) >= MAX_TASKS:
                    raise SchedulerError(
                        INVALID_TASK,
                        f"Input exceeds the limit of {MAX_TASKS} tasks.",
                    )

                dependencies = []
                if dependencies_text:
                    seen_dependencies = set()
                    for token in dependencies_text.split(DEPENDENCY_SEPARATOR):
                        dependency = token.strip(ASCII_WHITESPACE)
                        if not dependency or not TASK_ID_PATTERN.fullmatch(dependency):
                            raise SchedulerError(
                                INVALID_DEPENDENCY,
                                f"Task {task_id!r} has a malformed dependency.",
                            )
                        if dependency in seen_dependencies:
                            raise SchedulerError(
                                INVALID_DEPENDENCY,
                                f"Task {task_id!r} repeats dependency {dependency!r}.",
                            )
                        if dependency == task_id:
                            raise SchedulerError(
                                INVALID_DEPENDENCY,
                                f"Task {task_id!r} cannot depend on itself.",
                            )
                        seen_dependencies.add(dependency)
                        dependencies.append(dependency)

                tasks.append(
                    Task(task_id, duration, priority, tuple(dependencies))
                )
                task_ids.add(task_id)

            if not header_seen:
                raise SchedulerError(INVALID_CSV, "CSV file is missing its header.")

    except UnicodeDecodeError as error:
        raise SchedulerError(INVALID_CSV, "Input file is not valid UTF-8.") from error
    except csv.Error as error:
        raise SchedulerError(INVALID_CSV, f"Malformed CSV: {error}") from error
    except (OSError, ValueError) as error:
        raise SchedulerError(READ_ERROR, f"Could not read input file: {error}") from error

    known_ids = {task.task_id for task in tasks}
    for task in tasks:
        for dependency in task.dependencies:
            if dependency not in known_ids:
                raise SchedulerError(
                    INVALID_DEPENDENCY,
                    f"Task {task.task_id!r} depends on unknown task {dependency!r}.",
                )
    return tasks


def find_cycle(tasks):
    dependencies = {task.task_id: task.dependencies for task in tasks}
    state = {task.task_id: 0 for task in tasks}

    for start in dependencies:
        if state[start] != 0:
            continue

        path = [start]
        positions = {start: 0}
        state[start] = 1
        stack = [(start, 0)]

        while stack:
            task_id, next_dependency = stack[-1]
            task_dependencies = dependencies[task_id]
            if next_dependency == len(task_dependencies):
                stack.pop()
                path.pop()
                positions.pop(task_id)
                state[task_id] = 2
                continue

            dependency = task_dependencies[next_dependency]
            stack[-1] = (task_id, next_dependency + 1)
            if state[dependency] == 0:
                state[dependency] = 1
                positions[dependency] = len(path)
                path.append(dependency)
                stack.append((dependency, 0))
            elif state[dependency] == 1:
                return path[positions[dependency] :] + [dependency]

    return None


def schedule_tasks(tasks, workers):
    if not tasks:
        return [], 0

    dependents = {task.task_id: [] for task in tasks}
    remaining_dependencies = {}
    task_by_id = {task.task_id: task for task in tasks}
    ready = []

    for task in tasks:
        remaining_dependencies[task.task_id] = len(task.dependencies)
        for dependency in task.dependencies:
            dependents[dependency].append(task.task_id)
        if not task.dependencies:
            heapq.heappush(ready, (task.priority, task.task_id))

    idle_workers = list(
        range(WORKER_ID_BASE, WORKER_ID_BASE + workers)
    )
    heapq.heapify(idle_workers)
    running = []
    schedule = []
    current_time = 0
    completed_count = 0

    while completed_count < len(tasks):
        while running and running[0][0] == current_time:
            end_time, worker_id, task_id = heapq.heappop(running)
            heapq.heappush(idle_workers, worker_id)
            completed_count += 1
            for dependent in dependents[task_id]:
                remaining_dependencies[dependent] -= 1
                if remaining_dependencies[dependent] == 0:
                    task = task_by_id[dependent]
                    heapq.heappush(ready, (task.priority, task.task_id))

        while ready and idle_workers:
            _, task_id = heapq.heappop(ready)
            worker_id = heapq.heappop(idle_workers)
            task = task_by_id[task_id]
            end_time = current_time + task.duration
            schedule.append(
                {
                    JSON_TASK_ID_FIELD: task_id,
                    JSON_WORKER_ID_FIELD: worker_id,
                    JSON_START_FIELD: current_time,
                    JSON_END_FIELD: end_time,
                }
            )
            heapq.heappush(running, (end_time, worker_id, task_id))

        if completed_count == len(tasks):
            break
        current_time = running[0][0]

    schedule.sort(
        key=lambda entry: (
            entry[JSON_START_FIELD],
            entry[JSON_WORKER_ID_FIELD],
        )
    )
    makespan = max(entry[JSON_END_FIELD] for entry in schedule)
    return schedule, makespan


def error_document(error):
    detail = {
        JSON_CODE_FIELD: error.code,
        JSON_MESSAGE_FIELD: error.message,
    }
    if error.cycle is not None:
        detail[JSON_CYCLE_FIELD] = error.cycle
    return {
        JSON_STATUS_FIELD: "error",
        JSON_ERRORS_FIELD: [detail],
    }


def main(arguments=None):
    if arguments is None:
        arguments = sys.argv[1:]
    try:
        input_path, workers = parse_arguments(arguments)
        tasks = load_tasks(input_path)
        cycle = find_cycle(tasks)
        if cycle is not None:
            raise SchedulerError(
                CYCLE_DETECTED,
                "Dependency graph contains a cycle.",
                cycle,
            )

        schedule, makespan = schedule_tasks(tasks, workers)
        result = {
            JSON_STATUS_FIELD: "ok",
            JSON_WORKERS_FIELD: workers,
            JSON_MAKESPAN_FIELD: makespan,
            JSON_SCHEDULE_FIELD: schedule,
        }
        exit_code = SUCCESS_EXIT_CODE
    except SchedulerError as error:
        result = error_document(error)
        exit_code = ERROR_EXIT_CODE

    sys.stdout.write(json.dumps(result) + "\n")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
