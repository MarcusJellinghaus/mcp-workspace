# Step 1 — Cap the violation and stale-entry lists at 50

Read [summary.md](summary.md) first.

Single commit: tests + implementation + checks passing.

## WHERE

| File | Change |
|---|---|
| `tests/checks/test_file_sizes.py` | Add one module-level helper and four cases to the existing `TestRenderOutput` class (starts at line 122). |
| `src/mcp_workspace/checks/file_sizes.py` | Add two module-level constants after `logger` (line 10); modify `render_output` (lines 145-181). |

## WHAT

Two module-level constants, placed after `logger = logging.getLogger(__name__)`:

```python
_MAX_REPORT_VIOLATIONS = 50
_MAX_STALE_ENTRIES = 50
```

`render_output(result: CheckResult, max_lines: int) -> str` — **signature unchanged**. Body gains
two slices and two conditional notice lines.

No other function in the module changes. `check_file_sizes`, `render_allowlist`, `load_allowlist`,
`get_file_metrics` and `count_lines` are untouched.

## HOW

No new imports, no new decorators, no new dependency. The constants are module-private
(leading underscore), matching `search.py`'s `_MAX_LINE_CHARS` precedent named in #257.

Each constant carries a comment recording that the cap is deliberate and that no lift parameter
exists by design. Copy the established wording from `tree_listing.py:182-184` (the `list_directory`
250-line cap) rather than inventing one:

```python
# The 250-line cap is deliberate: list_directory has no lift parameter and
# is not getting one. Callers narrow instead - path=<subdir>, dirs_only=True,
# or search_files for targeted lookups.
```

Adapted, the two comments name the alternative that actually applies to each site — `.gitignore`
for violations (per the summary: the allowlist takes exact paths only, so it cannot narrow a
vendored tree), and nothing for stale entries beyond editing the allowlist itself.

## ALGORITHM

```
render violations:
    keep = result.violations[:_MAX_REPORT_VIOLATIONS]      # already sorted desc at :134
    emit "  - {path}: {n} lines" for each kept item
    if count > _MAX_REPORT_VIOLATIONS:
        emit "  ... showing {cap} of {count} violations (largest first)"
    emit "" then the unchanged remedy sentence

render stale entries:
    stale_count = len(result.stale_entries)
    emit header "\nStale allowlist entries ({stale_count}):"   # unchanged
    keep = result.stale_entries[:_MAX_STALE_ENTRIES]        # alphabetical at :127
    emit "  - {entry}" for each kept item
    if stale_count > _MAX_STALE_ENTRIES:
        emit "  ... showing {cap} of {stale_count} stale entries"   # no ordering claim
```

Reuse the counts already in scope: `count = len(result.violations)` exists at line 159, and bind
`stale_count = len(result.stale_entries)` once for both the header and the notice. Do not
introduce further locals.

## DATA

`render_output` still returns a single `"\n".join(lines)` string.

**Exact emitted notice strings** (assert these literally in tests):

```
  ... showing 50 of 845 violations (largest first)
  ... showing 50 of 312 stale entries
```

Both carry the same **two-space indent** as the `  - ` item lines they follow, and render
**immediately after the last listed item**.

**Placement:**

- The violations notice sits **before** the blank line and the closing remedy sentence currently
  emitted at `file_sizes.py:168-171`.
- The stale block (`file_sizes.py:176-179`) is the last thing `render_output` emits — no blank
  line and no remedy sentence follow it — so its notice simply ends the output.

**Unchanged output elements** — the pass-path summary line, the fail-path summary line
(`File size check failed: {count} file(s) exceed {max_lines} lines`), the
`Allowlisted files: {n}` line, the `Stale allowlist entries ({n}):` header, and the remedy
sentence `Consider refactoring these files or adding them to the allowlist.`

Note the fail-path summary reports the **true total** (`len(result.violations)`), not the capped
count. Both notices therefore restate a count already visible upstream — the summary says
"845 file(s)" and the stale header carries "(312)". **The redundancy is intentional**: the count
is what a reader needs at the end of a long list. This is not a review finding.

## Line-length note

The violations notice does not fit on one 88-char line at its indent level. Split it as adjacent
string literals with the `f` prefix on the interpolating part only — a second `f`-prefixed literal
with no placeholder trips pylint W1309:

```python
f"  ... showing {_MAX_REPORT_VIOLATIONS} of {count}"
" violations (largest first)"
```

## TESTS (write first)

Add to `tests/checks/test_file_sizes.py`. The module already imports `CheckResult`, `FileMetrics`
and `render_output`, and already has a `_write_file` helper — add one sibling helper beside it:

```python
def _metrics(count: int) -> List[FileMetrics]:
    """Helper: build *count* violations, largest first."""
```

It returns `FileMetrics(path=Path(f"src/f{i}.py"), line_count=1000 - i)` for `i` in `range(count)`,
which is already sorted descending, matching what `check_file_sizes` produces. The module has no
`typing` import today (it imports only `os`, `pathlib.Path` and `pytest`), so add a new
`from typing import List` line.

Extend the existing `mcp_workspace.checks.file_sizes` import with `_MAX_REPORT_VIOLATIONS` and
`_MAX_STALE_ENTRIES`; case 4 drives its item counts from them, which is what covers the
"both caps are named constants" criterion.

Four cases in `TestRenderOutput`:

1. **`test_violations_capped_at_50`** — `CheckResult(passed=False, violations=_metrics(845))`.
   Assert the notice string `"  ... showing 50 of 845 violations (largest first)"` is present;
   assert exactly 50 lines start with `"  - "`; assert `"845 file(s) exceed"` still appears; assert
   the remedy sentence still appears; assert the 51st path (`src/f50.py`) is absent.
2. **`test_stale_entries_capped_at_50`** — `CheckResult(passed=True, total_files_checked=5,
   stale_entries=[f"old{i:03d}.py" for i in range(312)])`. Assert
   `"  ... showing 50 of 312 stale entries"` is present; assert the header
   `"Stale allowlist entries (312):"` is intact; assert the notice is the **last** line of the
   output; assert the notice does **not** contain `"largest"`.
3. **`test_both_caps_fire`** — one `CheckResult(passed=False, ...)` with 60 violations, 60 stale
   entries and `allowlisted_count=3`. `passed=False` is required — the violations block only
   renders on the fail path. Assert both notices present, the fail summary line present, the
   `"Allowlisted files: 3"` line present, and the remedy sentence present. This case covers the
   "summary line, allowlist count and remedy sentence render unchanged" criterion.
4. **`test_exactly_50_no_notice`** — one `CheckResult(passed=False, ...)` with exactly
   `_MAX_REPORT_VIOLATIONS` violations and exactly `_MAX_STALE_ENTRIES` stale entries, sized from
   the constants rather than the literal 50. `passed=False` is required, as in case 3. Assert
   `"showing"` does not appear anywhere in the output, and that all items of both lists are listed
   (`_MAX_REPORT_VIOLATIONS + _MAX_STALE_ENTRIES` lines starting with `"  - "`). Driving the sizes
   from the constants is what ties the criterion "both caps are named constants" to a test; also
   assert both constants equal 50, so the literal notice strings asserted in cases 1-3 stay valid.

Also assert in at least one case that neither notice names a parameter — e.g. `"max_lines"` and
`"max_report"` absent from the notice lines.

Do **not** modify `tests/test_server_file_size.py` or the existing cases at
`tests/checks/test_file_sizes.py:131-160`. An unchanged `render_output` signature leaves both
unaffected; if either breaks, the implementation has drifted from the plan.

## CHECKS

```
mcp__mcp-tools-py__run_format_code
mcp__mcp-tools-py__run_pylint_check
mcp__mcp-tools-py__run_pytest_check   (extra_args: ["-n", "auto"])
mcp__mcp-tools-py__run_mypy_check
```

## LLM PROMPT

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_1.md`.
>
> Implement step 1 only: cap the violations and stale-entry enumerations in
> `render_output` (`src/mcp_workspace/checks/file_sizes.py`) at 50 each, behind the two named
> module-level constants `_MAX_REPORT_VIOLATIONS` and `_MAX_STALE_ENTRIES`, each carrying a
> deliberate-cap comment adapted from `tree_listing.py:182-184`.
>
> Write the four tests in `tests/checks/test_file_sizes.py` first, confirm they fail, then
> implement. Assert the two notice strings literally.
>
> Constraints: `render_output`'s signature must not change. Do not add a tool parameter. The
> notices must not name any parameter. Do not touch `tests/test_server_file_size.py`,
> `render_allowlist`, `check_file_sizes`, or `server.py`. Leave the summary lines, the allowlist
> count, the stale header and the remedy sentence exactly as they are.
>
> Then run format, pylint, pytest (`-n auto`) and mypy, and commit as
> `feat(file_sizes): cap violation and stale-entry reports at 50`.
