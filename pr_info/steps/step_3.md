# Step 3: Per-group time limits, documentation, final unit-group run

One commit: `test(guards): enforce per-group wall-clock time limits`

Read `pr_info/steps/summary.md`, `pr_info/steps/step_1.md` and `pr_info/steps/step_2.md` first. Issue #417 ("Guard 3", "Reporting", "Existing unit-group violations") is the full specification.

## Goal

A test whose setup + call + teardown wall-clock time exceeds its limit fails. The limit is its `time_limit` marker, otherwise its group's `test_time_limits` entry; a group with no entry has no limit. The failure message tells an automated agent to re-run before acting. `--no-time-limit` switches only this check off.

## WHERE

- Modified:
  - `tests/_guards.py`
  - `tests/test_guards.py`
  - `tests/README.md`
  - any test the final run surfaces (see Existing violations)

## Tests first (`tests/test_guards.py`)

1. **`test_time_limit`**: one in-process run, `-n 0`, with the default `_inner` limits (`unit: 0.5`), `time_limit(30, reason="in-process pytester run; inner tests sleep")`. Inner `test_time.py`:
   - `test_slow_fixture(slow_setup)`: the fixture sleeps 0.7 s and the body is empty. Expect a call-phase failure; setup time counts.
   - `@pytest.mark.time_limit(5, reason="r") test_override()`: sleeps 0.7 s. Expect a pass.
   - `test_pytrace_false()`: sleeps 0.7 s, then `pytest.fail("own message", pytrace=False)`. Expect a failure showing `own message` and the time note.
   - `test_slow_teardown(slow_teardown)`: the fixture sleeps 0.7 s after `yield`. Expect `ERROR at teardown of test_slow_teardown` with the time message.
   - `test_fast()`: expect a pass.
   - Assert:
     - `parseoutcomes()["failed"] == 2`
     - `test_override` and `test_fast` passed
     - stdout contains `test_time.py::test_slow_fixture`, `wall-clock`, `0.5 s` and `own message`
     - stdout contains this literal sentence, copied verbatim; don't import it from `_guards`:
       `re-run before changing anything; a single spike under xdist is not a reason to add `time_limit`, re-mark or rewrite the test — act only if it fails again.`
2. **`test_no_time_limit_keeps_git_guard`**: one subprocess run with `-n 0 --no-time-limit`, `time_limit(60, reason="subprocess pytester run; inner test starts git")`. Inner:
   - `test_slow()`: sleeps 0.7 s. Expect a pass.
   - `test_git()`: `subprocess.run(["git", "--version"], check=True, capture_output=True)`. Expect a failure with `test_git.py::test_git started a git process`.

## WHAT (`tests/_guards.py`)

```python
RERUN_NOTE = (
    "re-run before changing anything; a single spike under xdist is not a reason to add "
    "`time_limit`, re-mark or rewrite the test — act only if it fails again."
)

def _limit(item: pytest.Item) -> tuple[float, str] | None   # (seconds, source label) or None = no limit
```

`_report(item)` gains the time check next to the git check (step 2).

## HOW

- `_limit` reads `item.config.stash[_LIMITS]` (step 1). `None` means `--no-time-limit`.
- `_limit` reuses `_time_limit_seconds` (step 1) and `_group` (step 2).
- `_report` uses `state.start` (step 2) and `time.perf_counter()`.
- Module docstring:
  - the time limit and that it is wall-clock time
  - `time_limit(seconds, reason=...)`
  - `--no-time-limit` (for `--pdb`, breakpoints and profiling; usable via `run_pytest_check(extra_args=["--no-time-limit", ...])`)
  - the re-run rule
- `tests/README.md`: a short "Test guards" section. It names the three guards, the group markers, `time_limit` and `--no-time-limit`, and points to the `tests/_guards.py` docstring for details and limitations.

## ALGORITHM

### `_limit(item)`

```
limits = item.config.stash[_LIMITS]
if limits is None: return None                                        # --no-time-limit
mark = item.get_closest_marker("time_limit")
if mark: return _time_limit_seconds(mark), "its time_limit marker"
group = _group(item); return (limits[group], f"group {group!r}") if group in limits else None
```

### Addition to `_report(item)`, after the git check

```
limit = _limit(item); elapsed = time.perf_counter() - state.start
if "time" not in state.reported and limit and elapsed > limit[0]:
    state.reported.add("time")
    notes.append(f"{item.nodeid} took {elapsed:.2f} s wall-clock (setup + call + teardown so far), over the {limit[0]:g} s limit of {limit[1]}. "
                 f"The limit is wall-clock time, so machine load counts: {RERUN_NOTE} In CI, re-run the job. "
                 "If it fails again: speed the test up, give it the right group marker, or add @pytest.mark.time_limit(seconds, reason=\"...\").")
```

The call and teardown wrappers from step 2 stay unchanged. "Teardown error only when teardown alone pushes it over" follows from `state.reported`.

## DATA

`_limit` returns `(seconds, label)` or `None`. The time note is joined with any git note in `_report`'s single return string.

## Existing violations

Final unit-group run, as the implement workflow's last step does:

```
run_pytest_check(extra_args=["-n", "auto", "-m", "not git_integration and not github_integration"])
```

For any guard failure:
- re-run once; a single spike is not a reason to change a test
- if it fails again: speed the test up, give it the right group marker, or add `@pytest.mark.time_limit(<s>, reason="...")`

Then run the full suite (`-n auto`) and the serial performance run. Record each change in the commit message body.

## Checks

- pylint, `run_pytest_check(extra_args=["-n", "auto"])`, `run_pytest_check(markers=["performance"], extra_args=["-n", "0"])`, mypy, ruff, vulture.
- `check_file_size`: `tests/_guards.py` and `tests/test_guards.py` must each stay under 750 lines; otherwise add them to `.large-files-allowlist` with a reason.
- `run_format_code` before the commit.

## Blocked conditions

In each case below, write one line to `pr_info/.blocked.txt` and stop.

- A test keeps exceeding its limit after a re-run, and none of the three fixes (speed up, re-mark, `time_limit` with reason) fits.
- The time limit needs a new dependency (e.g. `pytest-timeout`).

## LLM prompt

> Read `pr_info/steps/summary.md`, `pr_info/steps/step_3.md` (and steps 1 and 2 for the existing helpers), and issue #417 ("Guard 3", "Reporting", "Existing unit-group violations"). Steps 1 and 2 are done. Implement step 3 only:
> - write `test_time_limit` and `test_no_time_limit_keeps_git_guard` in `tests/test_guards.py` first
> - then add `RERUN_NOTE`, `_limit` and the time check in `_report` to `tests/_guards.py`
> - update the module docstring and `tests/README.md`
> - run the unit group and the full suite, and handle violations as the step describes
>
> Use the MCP tools listed in `.claude/CLAUDE.md`. Run pylint, pytest (`-n auto`, plus the serial performance run), mypy, ruff, vulture and the file-size check until all pass, format the code, then make one commit. If a blocked condition applies, write one line to `pr_info/.blocked.txt` and stop.
