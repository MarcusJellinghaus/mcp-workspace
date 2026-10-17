# Step 4 — README documentation update

Read `pr_info/steps/summary.md` first. Documentation-only step; no production
code changes, no new tests (TDD doesn't apply to prose).

## Precondition

`README.md` still contains a line with `` `--project-dir`: (Required) `` near
line 74 and a line containing "is **required** for security reasons" near
line 80 (the exact line numbers may have drifted slightly; match on text, not
line number). If neither phrase is found anywhere in `README.md`, write one
line to `pr_info/.blocked.txt` and stop.

## WHERE

- `README.md`

## WHAT

No functions — text edits only, in the "Command Line Arguments" and the
paragraph right after it.

## HOW

- Replace `` - `--project-dir`: (Required) Directory to serve files from `` with
  wording that says the server still exits with code 1 if `--project-dir` is
  missing or invalid, but it is no longer enforced by `argparse`'s
  `required=True` (so `--help` works without it).
- Replace the sentence "The project directory parameter (`--project-dir`) is
  **required** for security reasons." with the same "exits 1 without it"
  framing, keeping the security rationale (all file operations restricted to
  this directory).
- Add one new bullet or sentence to the "Command Line Arguments" section
  stating that unrecognized arguments are ignored at startup and logged (one
  `WARNING` per argument plus a startup `INFO` line), rather than stopping the
  server.

## ALGORITHM

N/A — prose edit.

## DATA

N/A.

## Checks

No test suite changes. Run `run_pytest_check`, `run_pylint_check`,
`run_mypy_check` once more over the full repo as a final gate for the whole
feature (confirms steps 1-3 are still green together with this step).

## Commit

One commit: `docs(readme): document tolerant startup and unknown-argument handling`

## LLM prompt for this step

> Read `pr_info/steps/summary.md`, then implement exactly
> `pr_info/steps/step_4.md`: update `README.md` only, matching the two
> phrases described in the precondition. Run the full pytest/pylint/mypy
> suite via the MCP tools afterward as a final check for the whole issue
> #319 implementation. If the precondition does not hold, write one line to
> `pr_info/.blocked.txt` and stop.
