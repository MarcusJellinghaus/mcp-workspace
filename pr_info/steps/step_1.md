# Step 1 — Bug 1: UTF-8 decode chokepoint (`run_git_text`)

**Read `pr_info/steps/summary.md` first** (see "Bug 1" and "Architectural / Design
Changes" §1). This step fixes the cp1252 mangling and the resulting broken non-ASCII
`search` by introducing one decode chokepoint and routing all 12 read-only call sites
through it. One commit.

## WHERE
- `src/mcp_workspace/git_operations/core.py` — add helper.
- `src/mcp_workspace/git_operations/read_operations.py` — route all 12 call sites; import
  the helper.
- `tests/git_operations/test_read_operations.py` — add unit guard; fix broken mocks.

## WHAT

### New helper — `core.py`
```python
def run_git_text(repo: Repo, method: str, *args: str) -> str:
    """Run a git method and decode its output as UTF-8.

    Forces UTF-8 decoding of git stdout (GitPython otherwise decodes with the
    OS locale code page, e.g. cp1252 on Windows). Strips trailing newlines to
    match GitPython's string-mode output exactly.
    """
```
- `Repo` is already imported in `core.py` (`from git import Repo`).

### Route-through — `read_operations.py`
Replace each `repo.git.<cmd>(*args)` with `run_git_text(repo, "<cmd>", *args)`.
Add `from .core import run_git_text` (extend the existing `from .core import ...`).

The **12** call sites:
| Function | Call(s) to convert |
|----------|--------------------|
| `_run_simple_command` | `getattr(repo.git, git_method)(*cmd_args)` → `run_git_text(repo, git_method, *cmd_args)` |
| `git_log` | `repo.git.log(*cmd_args)` (inside `try`) |
| `git_diff` | `repo.git.diff(*base_args)` (compact plain); `repo.git.diff("--color=always", "--color-moved=dimmed-zebra", *base_args)` (compact ANSI); `repo.git.diff(*cmd_args)` (non-compact else) |
| `git_status` | `repo.git.status(*cmd_args)` |
| `git_merge_base` | `repo.git.merge_base(*safe_args)` (inside `try`) |
| `git_show` | `repo.git.show(*base_args)`; `repo.git.show("--color=always", "--color-moved=dimmed-zebra", *base_args)`; `repo.git.show(*cmd_args)` (non-compact else) |
| `git_branch` | `repo.git.branch(*safe_args)` |
| `git_check_ignore` | `repo.git.check_ignore(*cmd_args)` (inside `try`) |

## HOW (integration points)
- `try/except GitCommandError` blocks in `git_log`, `git_merge_base`, `git_check_ignore`
  stay put — they now wrap the `run_git_text(...)` call. The helper does **not** catch
  exceptions.
- Both compact-path git invocations (plain **and** `--color=always ...` ANSI) in
  `git_diff` and `git_show` must go through the helper, or `render_compact_diff` mixes
  clean and mojibake text.
- Do **not** change any downstream logic (`truncate_output`, `filter_*`, empty-checks,
  compact rendering). Only the raw-output acquisition changes.
- The local annotations `plain: str` / `ansi: str` / `output: str` at the routed call
  sites remain `str` (since `run_git_text` returns `str`), so **no** annotation changes
  or `# type: ignore` are needed — do not let a mypy pass drive edits here.

## ALGORITHM (`run_git_text`)
```
raw_bytes = getattr(repo.git, method)(*args, stdout_as_string=False)
text = raw_bytes.decode("utf-8", errors="replace")
return text.rstrip("\n")   # match GitPython string mode; keep empty-checks working
```

## DATA
- Returns `str` (UTF-8 decoded, trailing newlines stripped). Empty output → `""`
  (so existing `if not output:` messages still fire).

## TESTS (write first — TDD)

### A. New unit guard for `run_git_text` (the real Bug 1 regression guard)
CI runs a UTF-8 locale and would **not** reproduce the bug with real git, so this
injected-bytes test is the guard.
```python
def test_run_git_text_decodes_utf8_em_dash() -> None:
    mock_repo = MagicMock()
    # e2 80 94 == U+2014 em dash; returned as raw bytes (stdout_as_string=False)
    mock_repo.git.diff.return_value = b"analysing \xe2\x80\x94 done\n"
    result = run_git_text(mock_repo, "diff", "--no-ext-diff")
    assert result == "analysing — done"           # decoded, trailing \n stripped
    mock_repo.git.diff.assert_called_once_with(
        "--no-ext-diff", stdout_as_string=False
    )
```
Optionally add a second assertion that a search pattern containing the em-dash now
matches `result` (documents the search consequence). Import `run_git_text` from
`mcp_workspace.git_operations.core`.

Also add a test asserting the `errors="replace"` contract explicitly: feeding invalid
UTF-8 bytes (e.g. `b"bad \xff byte"`) to `run_git_text` decodes to the replacement char
`�` and does **not** raise (the sample test above only covers valid UTF-8).

### B. Fix broken mocks — switch `str` → `bytes`
Every mock whose value now flows through `run_git_text().decode()` must return `bytes`.
In `tests/git_operations/test_read_operations.py`:
- `test_log_hardcodes_safety_flags`: `mock_repo.git.log.return_value = b"mocked"`
- `test_diff_hardcodes_safety_flags`: `mock_repo.git.diff.return_value = b""`
- `test_status_with_pathspec`: `mock_repo.git.status.return_value = b"mocked status"`
  (assertion `result == "mocked status"` stays — decode yields `str`)
- `TestRunSimpleCommand`:
  - `test_validates_args`: `fetch.return_value = b"ok"`
  - `test_appends_pathspec`: `ls_files.return_value = b"file.txt"`
  - `test_truncates_output`: `ls_files.return_value = "\n".join(...).encode()`
  - `test_no_output_message`: `fetch.return_value = b""`
  - `test_includes_safety_flags`: `ls_tree.return_value = b"blob"`
  - `test_no_safety_flags`: `rev_parse.return_value = b"abc123"`

**Not affected** (do not change): `test_log_reraises_non_empty_repo_git_error` (uses
`side_effect` exception); all `TestGitDispatcher` tests (they patch `git_log`/`git_diff`/…
directly, above the `repo.git` layer). The `call_args[0]` positional assertions still hold
— `run_git_text` passes flags positionally and `stdout_as_string` as a kwarg.

## CHECKS (all must pass — CLAUDE.md)
- `mcp__tools-py__run_pylint_check`
- `mcp__tools-py__run_pytest_check` with
  `extra_args=["-n","auto","-m","not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"]`
  then also run the git integration slice:
  `markers=["git_integration"]` to confirm real-repo read paths still pass.
- `mcp__tools-py__run_mypy_check`

## COMMIT
`fix(git): decode read-only git output as UTF-8 via run_git_text chokepoint`
