# Assignment 1 — submission checklist

Submit this public implementation repository's URL with the separate public
Assignment 2 repository URL through the form supplied in the recruiter email.
No commit SHA is required. Do not include personal information, customer data,
or credentials.

## Running the work

- Language/runtime and version: Python 3.10 or later; verified with Python 3.12.10.
- Dependency installation command: `python -m pip install pytest` (scheduler runtime uses only the standard library).
- Exact scheduler command: `python scheduler.py --input inputs\basic.csv --workers 2`
- Exact test command: `pytest -q`
- Actual test results: `51 passed, 5 subtests passed in 10.38s` (Python 3.12.10, pytest 9.1.1).
- Data structures and approximate time/space complexity: Task-ID lookup and reverse dependency adjacency lists; iterative DFS for cycle detection; heaps for ready tasks, running completions, and idle workers. Validation and cycle detection are O(V + E); scheduling is O((V + E) log V) worst case; space is O(V + E + W), where V is task count, E is dependency count, and W is worker count.

## Scope and assistance

- Known limitations or unfinished work: None known against the published Assignment 1 specification. The scheduler implements the required priority policy and does not search for a globally optimal schedule.
- Documentation or libraries used: The assignment brief and specification; Python standard-library `csv`, `heapq`, `json`, `re`, `dataclasses`, and `unittest`; pytest for the pytest suite.
- AI assistance used: Claude and the Copilot AI assistant in VS Code helped with scheduler design, implementation, tests, and documentation. I reviewed the changes, ran the test suite, checked all seven supplied inputs against expected JSON values, and compared 500 generated acyclic graphs against an independent simulator. The scheduler itself does not call an AI service and requires no API key or external runtime service.

## Before submitting

- [x] The repository includes implementation, executable tests and reproducible instructions.
- [x] Standard output is one JSON document; errors exit nonzero without a partial schedule.
- [x] The program runs locally without AI/LLM services, API keys or paid accounts.
- [x] No credentials, customer data, dependency folders or build output are included.
- [ ] The repository is public and final work is on the default branch.
- [ ] I will leave submitted work unchanged; no corrections or resubmissions are accepted.

You have two days from receiving the assignment; the recruiter email supplies
the exact deadline (date, time and timezone), form URL and HR contact. Submit
both repository links once. Extensions are considered only for a valid reason
raised with HR; approval is not guaranteed and the deadline does not
automatically pause. Contact HR for tooling or accessibility adjustments. Only
candidates advancing receive a reply; next steps are communicated by email.
