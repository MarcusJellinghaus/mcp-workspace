# Step 1 — Foundation: module skeleton, helpers, exports, importlinter exception

## LLM prompt

> Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_1.md`).
> Implement Step 1 exactly as described. Follow TDD: write the tests first, then the
> source. Run pylint, mypy, pytest, lint-imports, and tach before finishing — all must
> be green. Produce one commit.

## WHERE

**Created**

- `src/mcp_workspace/git_operations/verification.py`
- `tests/git_operations/test_verification.py`

**Modified**

- `src/mcp_workspace/git_operations/__init__.py` — re-export `CheckResult` and `verify_git`.
- `.importlinter` — add `mcp_workspace.git_operations.verification -> subprocess` to the `subprocess_ban` `ignore_imports`.
- `tests/git_operations/test_init_exports.py` — bump expected `__all__` count from 33 to 35.

## WHAT

### `verification.py` — public API

```python
class CheckResult(TypedDict):
    ok: bool
    value: str
    severity: Literal["error", "warning"]
    error: NotRequired[str]
    install_hint: NotRequired[str]


def verify_git(project_dir: Path, *, actually_sign: bool = False) -> dict[str, object]:
    """Verify local git environment and (if configured) signing setup."""
```

In this step `verify_git` returns `{"overall_ok": True}` only. All actual checks are
added in subsequent steps.

### `verification.py` — private helpers

```python
def _get_config(repo: Repo, key: str, *extra_args: str) -> Optional[str]:
    """Read git config; return None if key is unset."""

def _run(args: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    """Run an external binary with subprocess discipline (DEVNULL stdin, capture, no shell)."""
```

## HOW

- `verification.py` imports: `subprocess`, `shutil`, `pathlib.Path`,
  `typing` bits, `git.Repo`, `git.exc.GitCommandError`, and from
  `.core` import `safe_repo_context`. (No `from .repository_status import is_git_repository`
  yet — Step 2 introduces the first call site.)
- **Logging:** `from mcp_coder_utils.log_utils import setup_logging, log_function_call`
  (per CLAUDE.md "Shared Libraries"). Do **not** use `logging.getLogger(__name__)` in
  this module. Decorate `verify_git`, `_get_config`, and `_run` with
  `@log_function_call`. (Future helper `_run_with_input` introduced in Step 7 will also
  be decorated.) This diverges from `github_operations/verification.py`, which still
  uses plain `logging` — see summary.md "Design choices" for rationale.
- `git_operations/__init__.py`:
  - Add `from mcp_workspace.git_operations.verification import CheckResult, verify_git`
  - Add `"CheckResult"` and `"verify_git"` to `__all__` (alphabetised — see test below).
- `.importlinter` `subprocess_ban` contract — extend the existing `ignore_imports` list:
  ```ini
  ignore_imports =
      mcp_workspace.git_operations.verification -> subprocess
  ```
  (subprocess_ban currently has no ignore_imports — this becomes the first line.)
- `test_init_exports.py`: change `assert len(__all__) == 33` to `assert len(__all__) == 35`.

## ALGORITHM

```
_get_config(repo, key, *extra):
    try: return repo.git.config("--get", key, *extra).strip() or None
    except GitCommandError: return None      # exit 1 = unset

_run(args, timeout):
    return subprocess.run(args,
                          stdin=subprocess.DEVNULL,
                          capture_output=True,
                          text=True,
                          check=False,
                          timeout=timeout)

verify_git(project_dir, *, actually_sign=False):
    result = {}
    # Tier 1, Tier 2, Tier 3 sections added in later steps.
    result["overall_ok"] = True
    return result
```

## DATA

- `verify_git` returns `dict[str, object]` containing exactly `{"overall_ok": True}` after this step.
- `_get_config` returns `Optional[str]` (stripped, or `None`).
- `_run` returns `subprocess.CompletedProcess[str]`.

## Tests (written first)

In `tests/git_operations/test_verification.py`:

- `test_verify_git_returns_dict_with_overall_ok` — calls `verify_git(tmp_path)`, asserts
  `result["overall_ok"] is True` and the result is a `dict`.
- `test_verify_git_keyword_only_actually_sign` — `verify_git(tmp_path, True)` raises
  `TypeError` (positional arg disallowed by signature).
- `test_get_config_returns_value_when_set` — patch a `Repo` mock so
  `repo.git.config("--get", "user.name")` returns `"Alice\n"`; helper returns `"Alice"`.
- `test_get_config_returns_none_when_unset` — mock raises `GitCommandError(1, "config")`;
  helper returns `None`.
- `test_get_config_passes_extra_args` — assert `repo.git.config` is called with
  `("--get", "commit.gpgsign", "--type=bool")` when extra arg supplied.
- `test_run_uses_subprocess_discipline` — patch `subprocess.run`, call `_run(["gpg", "--version"], timeout=5)`,
  assert it was invoked with `stdin=subprocess.DEVNULL`, `capture_output=True`,
  `text=True`, `check=False`, `timeout=5`.
- `test_run_timeout_propagates` — patch `subprocess.run` with
  `side_effect=subprocess.TimeoutExpired(cmd=["gpg"], timeout=5)`; assert calling
  `_run(["gpg", "--version"], timeout=5)` re-raises `subprocess.TimeoutExpired`
  unchanged (no swallowing). Place this test in the same class as the other
  `_run` tests.
- `test_check_result_typed_dict_minimal` — construct
  `CheckResult(ok=True, value="x", severity="error")`; assert mapping access works
  (smoke test for the TypedDict).

In `tests/git_operations/test_init_exports.py`:

- Existing two tests now verify count is 35 and that `verify_git` and `CheckResult` are
  in `__all__`.
- `test_all_remains_alphabetised` — assert that
  `list(mcp_workspace.git_operations.__all__) == sorted(mcp_workspace.git_operations.__all__)`
  after inserting `CheckResult` and `verify_git`. Either add this as a new test or
  extend the existing exports test with the same assertion. Guards against accidental
  ordering regression when new symbols are added.

## Acceptance for this step

- `mcp_workspace.git_operations.verify_git` and `mcp_workspace.git_operations.CheckResult`
  are importable.
- `verify_git(tmp_path)` returns `{"overall_ok": True}`.
- `lint-imports` passes (subprocess exception in place).
- `tach check` passes.
- All pylint / mypy / pytest checks pass.
