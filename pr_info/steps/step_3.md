# Step 3 — Porcelain swap, classification, debug logging, populated `error_category`

> **LLM prompt** — Read `pr_info/steps/summary.md` for context, then implement
> exactly this step. Make one commit at the end. Run `pylint`, `mypy`, and
> `pytest` (fast-mode unit tests first using `-m "not git_integration and not
> github_integration"`, then `markers=["git_integration"]`).

## Why this step exists

This is the actual fix. After step 2, `error_category` exists everywhere as
`None`. After step 3:

- `commit_staged_files()` invokes git porcelain so `commit.gpgsign` (and other
  signing config + hooks) is honored.
- Failures populate `error_category` according to the taxonomy.
- The broad `except Exception` is gone.
- Mock-based tests verify the porcelain call and classification logic.

## WHERE

```
src/mcp_workspace/git_operations/commits.py     # modify (the actual fix)
src/mcp_workspace/git_operations/workflows.py   # modify (validation paths get "validation_failed")
tests/git_operations/test_commits.py            # modify (new mock-based tests)
```

No new files. No imports change in `__init__.py`.

## WHAT

### `commits.py` — `commit_staged_files()`

**Signature unchanged**:
```python
def commit_staged_files(message: str, project_dir: Path) -> CommitResult: ...
```

**Logic changes**:

1. Validation paths (empty/whitespace message, not-a-repo, no staged files)
   return `error_category="validation_failed"` instead of `None`.

2. Inside `safe_repo_context`:
   - Read three signing-related config values once via
     `repo.config_reader().get_value(section, key, default="<unset>")` for
     `("commit", "gpgsign")`, `("gpg", "format")`, `("user", "signingkey")`.
   - Emit one debug line with the args being forwarded **and** the three
     config values.
   - Call `repo.git.commit("-m", message.strip())` (porcelain). **No**
     `--no-gpg-sign`, **no** `--no-verify`.
   - On success: read short hash via
     `repo.head.commit.hexsha[:GIT_SHORT_HASH_LENGTH]`, return
     `error_category=None`.

3. `except GitCommandError as e`:
   - Coerce stderr: `stderr_lower = str(e.stderr or "").lower()`.
   - Classify: if any of `("gpg", "signing", "secret key", "signing failed")`
     appears in `stderr_lower`, category is `"signing_failed"`; otherwise
     `"commit_failed"`.
   - Debug-log stderr truncated to the first 500 characters, exit status
     (`e.status`), and the command.
   - Return `success=False`, `error=<original message including stderr>`,
     `error_category=<classified>`.

4. **Drop** the `except Exception` clause entirely — leave only
   `(InvalidGitRepositoryError, GitCommandError)`. This resolves the
   `# TODO: narrow to GitCommandError` at that site.

5. **Docstring update**: add a sentence flagging that hooks
   (pre-commit / commit-msg) now run by default — this is a deliberate
   behavior change vs. the previous `repo.index.commit` call.

### `workflows.py` — `commit_all_changes()`

Update the validation paths' `error_category` from `None` to
`"validation_failed"`:
- Not-a-repo path.
- `stage_all_changes` returned False path.

The no-changes early-return stays `error_category=None` (it's a success).
The delegated `commit_result` from `commit_staged_files()` already carries
the right category — pass it through unchanged.

The broad `except Exception` in `workflows.py` is **out of scope** — leave
its TODO and its return literal (already `error_category=None` from step 2).

### `test_commits.py` — new mock-based tests

Add a new test class `TestCommitStagedFilesPorcelain` (or extend
`TestCommitOperations`) with these tests, all using `unittest.mock.patch` on
`mcp_workspace.git_operations.commits.safe_repo_context`:

1. **`test_invokes_porcelain_without_no_gpg_sign`**
   - Mock `safe_repo_context` to yield a `MagicMock` repo.
   - Configure `mock_repo.head.commit.hexsha = "a" * 40`.
   - Configure `mock_repo.config_reader().get_value.return_value = "<unset>"`.
   - Mock `is_git_repository` and `get_staged_changes` to bypass validation.
     Patch them where they are *used*, not where they are defined:
     `mcp_workspace.git_operations.commits.is_git_repository` and
     `mcp_workspace.git_operations.commits.get_staged_changes`.
   - Call `commit_staged_files("hello", project_dir)`.
   - Assert `mock_repo.git.commit.called`.
   - Assert `mock_repo.git.commit.call_args.args == ("-m", "hello")`.
   - Assert `"--no-gpg-sign"` is **not** in any positional arg.
   - Assert `result["error_category"] is None`.

2. **`test_classifies_error_category`** (parametrized)
   - Two cases:
     - `("gpg: signing failed: secret key not available", "signing_failed")`
     - `("pre-commit hook failed", "commit_failed")`
   - Configure `mock_repo.git.commit.side_effect = GitCommandError(...)` with
     the parametrized stderr.
   - Assert `result["success"] is False`.
   - Assert `result["error_category"] == expected_category`.
   - Assert raw stderr is in `result["error"]`.

3. **`test_validation_failures_set_validation_failed`** (parametrized)
   - Four cases — parametrize over all four: empty message, whitespace-only
     message, not-a-repo path, no-staged-files path. Use mocks for the
     message-validation cases and real-git fixture for the not-a-repo case
     (whichever is cleanest per case).
   - Assert `result["error_category"] == "validation_failed"`.

Existing real-git tests (`test_commit_staged_files`, `test_commit_all_changes`,
`test_commit_with_multiline_message`,
`test_commit_all_changes_no_changes_returns_success`) remain unchanged in
intent — they still pass because the porcelain commit produces an equivalent
result on a repo without signing configured (which is now guaranteed by
step 1's fixtures).

## HOW

- New imports in `commits.py`: none expected; `GitCommandError` is already
  imported.
- New imports in `test_commits.py`: `from unittest.mock import MagicMock,
  patch`; `from git.exc import GitCommandError`.
- Patch target for mocks: `mcp_workspace.git_operations.commits.
  safe_repo_context` (patch where it's *used*, not where it's defined).
- Logging: use the existing module-level `logger` in `commits.py`. Use
  `logger.debug(...)` so default log levels stay quiet.

## ALGORITHM

```
commit_staged_files(message, project_dir):
    if not message.strip():               return validation_failed
    if not is_git_repository:             return validation_failed
    if not get_staged_changes:            return validation_failed
    with safe_repo_context as repo:
        cfg = read three signing keys via config_reader (default "<unset>")
        logger.debug("git commit args + signing cfg ...", ...)
        try:
            repo.git.commit("-m", message.strip())
        except GitCommandError as e:
            stderr_lower = str(e.stderr or "").lower()
            category = "signing_failed" if any kw in stderr_lower else "commit_failed"
            logger.debug("stderr / status / cmd ...")
            return failure(error_category=category)
        hash = repo.head.commit.hexsha[:7]
        return success(error_category=None)
```

## DATA

Return shapes (all conform to the step-2 `CommitResult` TypedDict):

```python
# success
{"success": True, "commit_hash": "abc1234", "error": None, "error_category": None}

# validation
{"success": False, "commit_hash": None, "error": "<msg>", "error_category": "validation_failed"}

# signing failure
{"success": False, "commit_hash": None, "error": "Git error creating commit: ...gpg: signing failed...",
 "error_category": "signing_failed"}

# commit failure (hook, lock, etc.)
{"success": False, "commit_hash": None, "error": "Git error creating commit: ...",
 "error_category": "commit_failed"}
```

## Verification

- `pylint` clean — note the `# pylint: disable=broad-exception-caught` comment
  goes away with the dropped clause.
- `mypy --strict` clean — `Literal` discrimination on `error_category`
  type-checks.
- `pytest` fast unit tests pass.
- `pytest -m "git_integration"` passes — existing real-git tests still
  succeed because step 1's fixtures disabled signing locally.
- New mock tests pass.
- No `# TODO: narrow to GitCommandError` remaining in `commits.py` (confirm
  via grep).

## Commit message

```
fix(git_operations): honor commit.gpgsign in commit_staged_files (#180)

Switch commit_staged_files from GitPython plumbing (repo.index.commit) to
porcelain (repo.git.commit) so commit.gpgsign, user.signingkey, gpg.format,
gpg.program, and pre-commit/commit-msg hooks are all honored automatically.

Behavior change: hooks now run by default. The previous repo.index.commit
silently bypassed them, which was an implementation accident, not a
designed feature. Downstream mcp-coder users may see commits that
previously passed start failing on hook violations — this is correct.

Populates the new CommitResult.error_category with signing_failed,
commit_failed, or validation_failed per the issue's taxonomy.
Classification uses case-insensitive substring match on stderr against
("gpg", "signing", "secret key", "signing failed"). Non-English locales
fall through to commit_failed; raw stderr is still surfaced in `error`.

Drops the broad `except Exception` clause in commit_staged_files
(resolves an existing TODO at that site). The same TODO in workflows.py
and core.py is intentionally untouched (out of scope).

Mock-based tests verify the porcelain invocation does not pass
--no-gpg-sign, and assert classification of representative stderr
strings. Real-gpg end-to-end testing is too brittle across CI runners;
strong debug logging compensates by making real-world failures
self-diagnosing from logs alone.

Closes #180
```
