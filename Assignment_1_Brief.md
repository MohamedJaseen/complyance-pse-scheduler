# Complyance — Product Support Engineer
## Assignment 1: Dependency-Aware Job Scheduler

**Any programming language**

## Your task

Build a command-line program that reads tasks from a CSV file and produces a schedule for a given number of workers. Each task has a duration, priority and dependencies.

This is a simulation: calculate when tasks would run, without executing them or waiting in real time.

## Input example

```csv
task_id,duration,priority,dependencies
A,3,2,
B,2,1,A
C,4,1,
D,1,2,"B,C"
```

Your program accepts `--input PATH --workers W` and returns JSON containing the worker count, total completion time (`makespan`) and each task's worker, start and end time.

## Core rules

- A task starts only after all its dependencies finish.
- Each worker runs one task at a time; tasks cannot be interrupted.
- Choose ready tasks by priority: **smaller number first**, then task ID in ASCII order.
- Assign tasks to the lowest-numbered idle workers. Process all simultaneous completions before choosing new work.
- Keep workers busy whenever tasks are ready. Jump directly to the next completion when waiting.
- Reject invalid input, unknown dependencies and cycles with a useful error. Never return a partial schedule for invalid input.

Follow this policy exactly; you do not need to find a globally optimal schedule.

## Expected result for two workers

| Task | Worker | Start | End |
| --- | --- | --- | --- |
| C | 1 | 0 | 4 |
| A | 2 | 0 | 3 |
| B | 2 | 3 | 5 |
| D | 1 | 5 | 6 |

The makespan is **6 virtual time units**. Supplied examples include ties, idle periods, simultaneous completions and invalid graphs.

## What to submit

Submit one public repository link for this assignment, with final work on the default branch. Include:

- Your implementation and executable tests.
- A README with setup, run/test commands and actual test results.
- A short explanation of your approach, limitations and any AI assistance used.

No commit SHA, deployment, UI, server, database or architecture presentation is required. Use standard CSV/testing libraries, but implement the scheduling logic yourself.

**AI-assisted coding is allowed. The program itself must run without AI/LLM integration, API keys or external services.**

You have two days from receiving the assignment; the recruiter email supplies the exact deadline (date, time and timezone), submission form URL and HR contact. Submit both assignments once through that form, using two public repositories, one per assignment. No corrections or resubmissions are accepted; leave submitted work unchanged. Extensions are considered only for a valid reason raised with HR and are not automatic. Contact HR for tooling or accessibility adjustments. Only candidates advancing receive a reply; next steps are communicated by email.

## Full requirements and sample files

Read **`SPECIFICATION.md` before implementation** for the exact CSV limits, output/error schemas, validation rules and required test coverage. See `README.md` for the seven sample inputs and expected outputs, and complete `SUBMISSION.md` in your repository.
