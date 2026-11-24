# Step 6 — Marker audit (task 4, decisions 1 and 2)

## LLM prompt

Read `pr_info/steps/summary.md`, then implement this step (`pr_info/steps/step_6.md`) only. Add `git_integration` to the unit-group tests that start git in the modules listed below, and narrow or remove markers per decision 1, using the marker scope rule in the summary. Ensure no test carries two group markers. Verify with `--collect-only` and by running the changed files, then pylint and mypy, and produce exactly one commit. No measurement runs: task 5's counter run verifies.

## WHERE

Unit-group modules found starting git at analysis time:
- `tests/git_operations/`: `test_conflicts.py`, `test_rebase.py`, `test_rebase_probe.py`, `test_list_tree.py`, `test_origin_fetch.py` (partly marked), `test_push_current_branch.py` (partly marked), `test_eol_attribute.py`, `test_edge_cases.py`
- `tests/file_tools/`: `test_move_git_integration.py`, `test_line_endings_file_tools.py`, `test_line_endings.py`
- `tests/`: `test_credential_scrubbing.py` (partly marked)
- `tests/toolset/`: `test_reference_freshness.py`

Also check that these start no git after steps 2–3 and carry no marker: `tests/github_operations/issues/test_manager_base_branch.py`, `tests/test_server_get_base_branch.py`, `tests/checks/test_branch_status_base_branch.py`.

## WHAT

Marker edits only: `pytestmark = pytest.mark.git_integration`, a class decorator, or a per-test `@pytest.mark.git_integration`. No logic changes.

## HOW

- For each test, decide by reading the code ("How to tell by reading that a test starts git" in the summary): repo fixtures, `Repo.init`/clone, `repo.git.*`, `git.Git`, `subprocess` git, or unmocked `src` code that runs git.
- Apply the marker scope rule (module → class → per-test, fewest edits; no moving tests between classes).
- Partly marked modules: extend the existing markers to the unmarked tests that start git. Where a module-level `pytestmark` becomes correct, replace the per-scope decorators with it.
- Decision 2: `github_integration` / `performance` tests get no `git_integration`, even if they start git. Search the changed files for tests carrying two of `git_integration`, `github_integration`, `performance` and fix any found.
- Tests skipped on Windows: judge by reading the code, same rule.
- Don't create `git_slow_integration` (decided in task 5).

## ALGORITHM

```
for module in list:
    starts = {test: reads_as_starting_git(test) for test in module}
    if all(starts): set module pytestmark
    else per class: all → class marker; none → no marker; mixed → per-test markers
    remove markers from scopes where none start git
```

## DATA

None.

## Tests / checks

- `run_pytest_check(extra_args=["--collect-only", "-q", <changed files>])` must collect without errors (`--strict-markers` is in `addopts`).
- `run_pytest_check(extra_args=["-n", "auto", <changed files>])`.
- `run_pylint_check`, `run_mypy_check`, `run_format_code`.

## Commit

`test: mark unit-group tests that start git as git_integration`
