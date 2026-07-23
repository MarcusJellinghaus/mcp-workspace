# Step 2 — Bug 2: content-aware search for `git show <blob>`

**Read `pr_info/steps/summary.md` first** (see "Bug 2" and "Architectural / Design
Changes" §2–§3). This step fixes `search` returning "No matches" on `git show HEAD:<file>`
(file content, not a diff). Locale-independent; independent of Step 1. One commit.

## WHERE
- `src/mcp_workspace/git_operations/output_filtering.py` — add `filter_content_output`.
- `src/mcp_workspace/git_operations/read_operations.py` — select the filter in `git_show`.
- `tests/git_operations/test_output_filtering.py` — unit tests for the new filter.
- `tests/git_operations/test_read_operations.py` — real-repo integration guard.

## WHAT

### New filter — `output_filtering.py`
```python
def filter_content_output(text: str, search: str, context: int = 3) -> str:
    """Line-based grep for plain content (not a diff).

    Returns lines matching `search` (case-insensitive) plus `context` lines
    before/after each match. Sibling to filter_diff_output / filter_log_output.
    """
```
Reuse the exact sibling messages:
- no matches → `f"No matches for search pattern '{search}'"`
- bad regex → `f"Invalid search pattern: {e}"`

### `git_show` wiring — `read_operations.py`
Replace the tail of `git_show`:
```python
if search:
    output = filter_diff_output(output, search, context)
```
with:
```python
if search:
    if has_colon:
        output = filter_content_output(output, search, context)
    else:
        output = filter_diff_output(output, search, context)
```
`has_colon` is already computed earlier in `git_show`. Add
`filter_content_output` to the existing `from .output_filtering import (...)` import.
`git_diff` is **untouched** (its output is always a real diff).

`git_show` still applies `truncate_output(output, max_lines)` **after**
`filter_content_output`, so existing truncation semantics are intentionally preserved (a
large filtered result can still be truncated). No behavior change.

## HOW (integration points)
- Keep `filter_content_output` self-contained (KISS) — do **not** refactor a shared
  grep helper with `_filter_hunks`.
- Placement: define it beside `filter_diff_output` in `output_filtering.py`; no new
  imports beyond the already-present `re`.
- **Non-contiguous match groups:** when matches whose ±context windows don't overlap
  produce separate kept-line groups, the helper joins the kept lines directly with `\n`
  **without** a grep-style `--` gap separator. This is a deliberate accepted
  simplification — it keeps the helper self-contained (~12 lines), consistent with the
  plan's existing KISS notes. Match-correctness is unaffected; it is purely a display
  nuance. Do **not** add separator logic.

## ALGORITHM (`filter_content_output`)
```
try: pattern = re.compile(search, re.IGNORECASE)
except re.error as e: return f"Invalid search pattern: {e}"
lines = text.splitlines()
keep = set()
for i, line in enumerate(lines):
    if pattern.search(line):
        keep.update(range(max(0, i - context), min(len(lines), i + context + 1)))
if not keep: return f"No matches for search pattern '{search}'"
return "\n".join(lines[i] for i in sorted(keep))
```

## DATA
- Returns `str`: newline-joined matching lines (± context), or a message string.

## TESTS (write first — TDD)

### A. `filter_content_output` unit tests — `test_output_filtering.py`
Add a `TestFilterContentOutput` class using a small `SAMPLE_CONTENT` multi-line string
(e.g. containing the line `Fetch the issue`). Cover:
- match returns the matching line;
- `context=1` includes the adjacent line, `context=0` does not;
- no-match returns `"No matches for search pattern '...'"` (assert `"No matches"` +
  the pattern text);
- case-insensitive (`FETCH` matches `Fetch`);
- invalid regex (`"[unclosed"`) → result starts with `"Invalid search pattern:"`.

### B. Real-repo integration guard — `test_read_operations.py` (`@pytest.mark.git_integration`)
```python
def test_show_blob_search_matches_content(
    self, git_repo_with_commit: tuple[Repo, Path]
) -> None:
    repo, project_dir = git_repo_with_commit
    (project_dir / "notes.txt").write_text("intro\nFetch the issue\noutro\n")
    repo.index.add(["notes.txt"])
    repo.index.commit("add notes")
    result = git_show(project_dir, args=["HEAD:notes.txt"], search="Fetch the issue")
    assert "Fetch the issue" in result
    assert "No matches" not in result
```

## CHECKS (all must pass — CLAUDE.md)
- `mcp__tools-py__run_pylint_check`
- `mcp__tools-py__run_pytest_check` with the fast exclusion set, then
  `markers=["git_integration"]` for the integration guard.
- `mcp__tools-py__run_mypy_check`

## COMMIT
`fix(git): use line-based filter for show <blob> search (content, not diff)`
