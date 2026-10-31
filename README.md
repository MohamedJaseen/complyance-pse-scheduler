# Dependency-Aware Job Scheduler

A command-line scheduler that reads tasks from CSV and simulates their execution
on a fixed number of workers. It uses virtual time; it does not execute tasks or
sleep between events.

## Requirements

- Python 3.10 or later
- pytest to run the test suite

The scheduler itself uses only the Python standard library. To install pytest if
it is not already available:

```powershell
python -m pip install pytest
```

## Run

From the repository root:

```powershell
python scheduler.py --input inputs\basic.csv --workers 2
```

The program writes one JSON document to standard output. Successful runs exit
with code 0; invalid arguments, unreadable input, invalid CSV/task data,
dependency errors, or cycles return a nonzero exit code and an error JSON
document without a partial schedule.

The CSV header must be exactly:

```csv
task_id,duration,priority,dependencies
```

Multiple dependencies are comma-separated inside the dependencies field, which
must be quoted when it contains commas, for example `"B,C"`.

## Test

Run the suite from the repository root:

```powershell
pytest -q
```

Latest result:

```text
...................................................                 [100%]
51 passed, 5 subtests passed in 10.38s
```

Tests invoke the command-line program with subprocesses and also test its core
functions directly. Coverage includes all seven supplied examples, scheduling
order and worker selection, forward and multiple dependencies, simultaneous
completions, idle intervals, cycle witnesses, validation errors, empty input,
UTF-8 BOM/CRLF handling, 32 workers, and a 2,000-task dependency chain.
A separate deterministic differential check compared the scheduler with an
independent reference simulator on 500 randomly generated acyclic graphs; all
500 schedules matched.

## Approach

Tasks are stored by ID, with each task's dependency list and a reverse list of
dependents. An iterative depth-first search follows task-to-dependency edges and
returns a closed path when it finds a back edge. Scheduling uses a min-heap for
ready tasks, keyed by priority and ASCII task ID, a min-heap of idle worker IDs,
and a min-heap of running task completion times. The simulation processes all
tasks completing at a virtual instant before assigning newly ready work, then
jumps directly to the next completion.

For V tasks and E dependency edges, CSV validation and cycle detection take
O(V + E) time. Heap operations make scheduling O((V + E) log V) time in the
worst case. The task graph, heaps, and output use O(V + E + W) space.

## Limitations and assistance

There are no known unfinished requirements against the published Assignment 1
specification. This implementation intentionally follows the specified
priority-based scheduling policy; it does not search for a globally optimal
schedule.

Claude and the Copilot AI assistant in VS Code helped with the scheduler
design, implementation, tests, and documentation. I reviewed the changes, ran
the tests, compared all seven supplied examples with their expected JSON
values, and checked 500 generated acyclic graphs against an independent
simulator. The scheduler itself uses no AI service, API key, or external
runtime service.
