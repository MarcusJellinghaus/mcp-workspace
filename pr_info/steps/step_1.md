# Step 1 — Pytest timeout config (task 0, decision 7)

## LLM prompt

Read `pr_info/steps/summary.md`, then implement this step (`pr_info/steps/step_1.md`) only. Add the `pytest-timeout` key to `pyproject.toml` as specified below, run the checks listed, and produce exactly one commit. Do not touch any other file.

## WHERE

- `pyproject.toml`, section `[tool.mcp-tools-py]` (currently holds only `formatter = "ruff"`)

## WHAT

Add one key:

```toml
[tool.mcp-tools-py]
# Formatter for run_format_code and mcp-coder workflows: ruff (import sorting + ruff format)
formatter = "ruff"
# Timeout (s) for run_pytest_check. Must stay >= 1800: it outranks the 1800 s the
# toolkit sets for its longer test depths (test@standard, test@unattended).
pytest-timeout = 2400
```

## HOW

- Key name exactly `pytest-timeout`. Unknown keys are ignored silently. Do **not** use `check-timeout`: that one applies to every tool.
- Integer value, no quotes.

## ALGORITHM

None (config only).

## DATA

None.

## Tests / checks

- No new test (config only).
- Run `run_pytest_check` on one small file to confirm the config still loads, e.g. `extra_args=["-n", "auto", "tests/github_operations/issues/test_base.py"]`.
- `run_pylint_check`, `run_mypy_check`, `run_format_code`.

## Commit

`chore(tests): set mcp-tools-py pytest-timeout to 2400s`
