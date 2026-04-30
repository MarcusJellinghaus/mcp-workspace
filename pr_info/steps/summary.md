# Issue #181 — `verify_git` for local git environment & signing health checks

## Goal

Add a library function `verify_git(project_dir, *, actually_sign=False)` that returns
structured per-check results for the local git environment, focused on commit-signing
configuration. The function distinguishes:

- **not configured** (`signing_intent.value="not configured"`, `overall_ok=True`)
- **configured and working** (`overall_ok=True`)
- **configured but broken** (`overall_ok=False`, with the broken check at `severity="error"`)

Library-only — not registered as an MCP tool, not added to `server.py`. The companion
mcp-coder issue will wire it into `mcp-coder verify`.

## Architectural / design changes

| Change | File | Why |
|---|---|---|
| New module `git_operations/verification.py` | `src/mcp_workspace/git_operations/verification.py` | Mirrors `github_operations/verification.py`. Owns its own `CheckResult` (no GitHub-specific token fields — Decision #1). |
| Re-export `verify_git` and `CheckResult` from the package | `src/mcp_workspace/git_operations/__init__.py` | Public surface. Mirrors how `github_operations/__init__.py` re-exports its `verify_github` + `CheckResult`. |
| Carve out a narrow subprocess exception | `.importlinter` (`subprocess_ban` contract) | Production code is currently subprocess-banned. `verification.py` is the only legitimate consumer (gpg/ssh-keygen/gpgsm/gpg-connect-agent — Decision #5). Exception is scoped to `mcp_workspace.git_operations.verification` only. |
| Bump hard-coded export count | `tests/git_operations/test_init_exports.py` | Existing test asserts `len(__all__) == 33`. Becomes 35 after exporting `CheckResult` + `verify_git`. |

No changes to `tach.toml` — `git_operations` already has the right layer + dependencies.
No changes to `server.py` — library-only function.

## Module / file inventory

### Created

- `src/mcp_workspace/git_operations/verification.py` — the new module.
- `tests/git_operations/test_verification.py` — unit tests.
- `pr_info/steps/summary.md` — this file.
- `pr_info/steps/step_1.md` … `step_7.md` — per-step plans.

### Modified

- `src/mcp_workspace/git_operations/__init__.py` — add `verification` import + `__all__` entries.
- `.importlinter` — add `mcp_workspace.git_operations.verification -> subprocess` to the `subprocess_ban` `ignore_imports`.
- `tests/git_operations/test_init_exports.py` — bump expected `__all__` count from 33 to 35.

## Design choices (KISS-driven)

- **Logging via `mcp_coder_utils.log_utils` + stdlib `logging`.** `verification.py`
  imports `log_function_call` from `mcp_coder_utils.log_utils` (see shared-libraries
  section in CLAUDE.md) and also defines `logger = logging.getLogger(__name__)` at
  module top — both coexist per the project pattern in `base_manager.py` and the
  rest of `github_operations/*`. The public `verify_git` and any non-trivial helpers
  (`_get_config`, `_run`, `_run_with_input`) are decorated with `@log_function_call`
  for entry/exit; inline `logger.debug(...)` calls handle per-step diagnostics
  (truncated stderr, signature produced/failed, etc.) which the decorator does not
  provide. `setup_logging` is **not** imported here — it is only called from
  `main.py`. This still diverges from `verify_github`, which uses plain `logging`
  without the decorator; per project convention (CLAUDE.md "Shared Libraries") and
  explicit user direction, the new module adds `@log_function_call`.
- **One module, one public function.** No per-tier sub-functions. `verify_git()` is a
  single linear function with three commented sections (Tier 1 / Tier 2 / Tier 3),
  mirroring the structure of `verify_github()`.
- **Two tiny private helpers.**
  - `_get_config(repo, key, *extra_args) -> Optional[str]` — wraps
    `repo.git.config("--get", key, *extra_args)`, catches `GitCommandError`, returns
    `None` for unset keys. Used both for plain reads and for `--type=bool` reads (caller
    compares the returned string to `"true"`).
  - `_run(args, timeout) -> CompletedProcess[str]` — list-form args,
    `stdin=subprocess.DEVNULL`, `capture_output=True`, `check=False`, explicit
    `timeout`. The single chokepoint that enforces subprocess discipline.
- **`verify_head` uses GitPython, not subprocess.** `repo.git.verify_commit("HEAD")`
  inside `safe_repo_context` — git itself is owned by GitPython per Decision #5, so
  there's no second `shutil.which("git")` and no second timeout argument.
- **No `CheckResult` builder.** The TypedDict constructor is already terse;
  `verify_github` doesn't use one.
- **Tier 2 keys are absent (not present with `value="skipped"`) when no signing intent.**
  Decision #3.
- **`overall_ok` = all `severity="error"` checks pass.** Same rule as `verify_github`.
  Absent keys naturally don't participate.

## CheckResult shape (local to this module)

```python
class CheckResult(TypedDict):
    ok: bool
    value: str
    severity: Literal["error", "warning"]
    error: NotRequired[str]
    install_hint: NotRequired[str]
```

No `token_source` / `token_fingerprint` — those are GitHub-specific.

## Function signature

```python
def verify_git(project_dir: Path, *, actually_sign: bool = False) -> dict[str, object]:
    """Verify local git environment and (if configured) signing setup."""
```

Returns a dict with `overall_ok: bool` plus per-check `CheckResult` entries. Keys
present depend on what was configured (Tier 2 absent if no signing intent; Tier 3 only
when `actually_sign=True`).

## Implementation step map

| Step | Adds | New keys in result | Tests |
|---|---|---|---|
| 1 | Foundation: module, helpers, exports, importlinter exception, function skeleton returning `{"overall_ok": True}` | `overall_ok` | helpers in isolation, exports, structural |
| 2 | Tier 1 baseline | `git_binary`, `git_repo`, `user_identity` | per-check pass/fail |
| 3 | Tier 1 signing detection | `signing_intent`, `signing_consistency` | "not configured" vs detected; truthy parsing (`yes`/`on`/`1`); single-key concatenation |
| 4 | Tier 2 config-only | `signing_format`, `signing_key` | per-flag severity (Decision #10); unknown format → error |
| 5 | Tier 2 binary checks | `signing_binary`, `signing_key_accessible` | `gpg.program` precedence + missing-file hard error (Decision #13); ssh / x509 paths |
| 6 | Tier 2 auxiliaries | `agent_reachable`, `allowed_signers`, `verify_head` | warning-only severity; opportunistic skip via `repo.head.is_valid()` |
| 7 | Tier 3 opt-in deep probe | `actual_signature` | `actually_sign=False` never invokes; openpgp signs fixed probe; ssh/x509 → "not implemented" warning |

Each step is one commit: tests + implementation + all checks (pylint, mypy, pytest, lint-imports, tach) green.

## Sensitive-data handling (Decision #11)

Across all steps:
- Debug-log config values, resolved binary paths (`shutil.which` outcome), subprocess
  command + exit code + truncated stdout/stderr (cap ~500 chars), and the resulting
  `CheckResult`.
- **Never** log the signing key ID, key fingerprint, key file contents, or the produced
  signature bytes from `actual_signature`.
- Skip success-path debug logging for `git_binary` / `git_repo` (most frequent, lowest
  diagnostic value).

## Out of scope

- Wiring into `mcp-coder verify` (companion issue).
- SSH / x509 deep-probe in Tier 3 (returns "not implemented" warning).
- Auto-fix / interactive setup helpers.
- Real-gpg integration test in CI (manual integration test stays on the developer machine).
- Non-signing git environment checks (hook integrity, remote reachability, etc.).
- ssh `signing_key_accessible`: agent-loaded keys not detected — only file existence at the configured `user.signingkey` path is checked.
