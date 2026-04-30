# Step 2 — Tier 1 baseline checks: `git_binary`, `git_repo`, `user_identity`

## LLM prompt

> Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_2.md`).
> Build on Step 1's foundation. Implement the three Tier 1 baseline checks following
> TDD. Run pylint, mypy, pytest, lint-imports, and tach before finishing. Produce one
> commit.

## WHERE

**Modified**

- `src/mcp_workspace/git_operations/verification.py` — add three checks inside `verify_git`.
- `tests/git_operations/test_verification.py` — extend with classes for each check.

## WHAT

Three checks, each populating one `CheckResult` regardless of earlier failures.

| Key | Probe | Severity | OK condition |
|---|---|---|---|
| `git_binary` | `shutil.which("git")` then `_run([resolved, "--version"], 5)` | error | rc==0 and stdout contains `"git version"` |
| `git_repo` | `is_git_repository(project_dir)` | error | True |
| `user_identity` | `_get_config(repo, "user.name")` and `_get_config(repo, "user.email")` | error | both non-None |

`overall_ok` is now `all(c["ok"] for c in result.values() if isinstance(c, dict) and c["severity"] == "error")`.

## HOW

- Import `is_git_repository` from `.repository_status` inside `verification.py`.
- Use `safe_repo_context` to read user.name / user.email; if `git_repo` failed, skip the
  config reads but still emit a `user_identity` `CheckResult` with `ok=False`,
  `error="repository not accessible"`.
- `git_binary` uses the bare string `"git"` (not the resolved path) for cross-platform
  consistency in the `value` field; the resolved path goes into the debug log only.
- `install_hint` strings:
  - `git_binary`: `"Install git from https://git-scm.com/downloads"`
  - `user_identity`: `"Set user.name and user.email via 'git config --global user.{name,email}'"`

## ALGORITHM

```
# git_binary
path = shutil.which("git")
if path is None:
    result["git_binary"] = CheckResult(ok=False, value="not found",
                                        severity="error", error="git not on PATH",
                                        install_hint=...)
else:
    proc = _run([path, "--version"], timeout=5)
    if proc.returncode == 0 and "git version" in proc.stdout:
        result["git_binary"] = CheckResult(ok=True, value=proc.stdout.strip(),
                                            severity="error")
    else:
        result["git_binary"] = CheckResult(ok=False, value="found but not runnable",
                                            severity="error",
                                            error=(proc.stderr or "").strip()[:500])

# git_repo
result["git_repo"] = (CheckResult(ok=True, value=str(project_dir), severity="error")
                      if is_git_repository(project_dir)
                      else CheckResult(ok=False, value="not a git repo",
                                       severity="error",
                                       error=f"{project_dir} is not a git repository"))

# user_identity
if result["git_repo"]["ok"]:
    with safe_repo_context(project_dir) as repo:
        name = _get_config(repo, "user.name")
        email = _get_config(repo, "user.email")
    missing = [k for k, v in [("user.name", name), ("user.email", email)] if v is None]
    if missing:
        result["user_identity"] = CheckResult(ok=False, value=f"missing: {', '.join(missing)}",
                                              severity="error", error="...", install_hint="...")
    else:
        result["user_identity"] = CheckResult(ok=True, value=f"{name} <{email}>",
                                              severity="error")
else:
    result["user_identity"] = CheckResult(ok=False, value="unknown",
                                          severity="error",
                                          error="repository not accessible")

# overall_ok recomputed at the end
result["overall_ok"] = all(c["ok"] for c in result.values()
                           if isinstance(c, dict) and c.get("severity") == "error")
```

## DATA

Result keys after this step (in addition to `overall_ok`): `git_binary`, `git_repo`,
`user_identity`.

## Tests (written first)

Class `TestGitBinary`:
- `test_git_binary_ok` — patch `shutil.which` → `"/usr/bin/git"`, patch `_run` → returncode 0, stdout `"git version 2.42.0"` → `ok=True`.
- `test_git_binary_not_on_path` — patch `shutil.which` → `None` → `ok=False`, `value="not found"`, `severity="error"`.
- `test_git_binary_runnable_failure` — `shutil.which` succeeds but `_run` returncode 1 → `ok=False`, error captured.

Class `TestGitRepo`:
- `test_git_repo_ok` — patch `is_git_repository` → True → `ok=True`.
- `test_git_repo_missing` — patch → False → `ok=False`, `severity="error"`.

Class `TestUserIdentity`:
- `test_user_identity_ok` — both `_get_config` calls return strings → `ok=True`, value contains email.
- `test_user_identity_missing_name` — name → None, email → set → `ok=False`, value mentions `user.name`.
- `test_user_identity_missing_email` — symmetric.
- `test_user_identity_skipped_when_no_repo` — `is_git_repository` False → `ok=False`, `error="repository not accessible"`.

Class `TestOverallOk`:
- `test_overall_ok_true_when_all_pass` — patch the three checks all OK.
- `test_overall_ok_false_when_git_binary_fails` — verify failure of any error-tier check flips `overall_ok=False`.

Use a single `_patch_baseline_ok(...)` helper analogous to `_patch_all_ok` in the
GitHub test file. Mock `shutil.which`, `subprocess.run` (via a `side_effect`
dispatching by `argv[0]`), `is_git_repository`, and `safe_repo_context` (yielding a
`Mock` whose `.git.config` is configured per test).

## Acceptance for this step

- Calling `verify_git(tmp_path)` on a happy-path mock returns
  `{"git_binary": ..., "git_repo": ..., "user_identity": ..., "overall_ok": True}`.
- Each check fails independently (one failure does not prevent the others from running).
