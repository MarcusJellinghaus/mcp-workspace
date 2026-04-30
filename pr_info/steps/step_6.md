# Step 6 — Tier 2 auxiliaries: `agent_reachable`, `allowed_signers`, `verify_head`

## LLM prompt

> Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_6.md`).
> Add the three warning-tier Tier 2 auxiliary checks. Follow TDD. Run pylint, mypy,
> pytest, lint-imports, and tach. Produce one commit.

## WHERE

**Modified**

- `src/mcp_workspace/git_operations/verification.py` — append the three checks inside
  the Tier 2 block.
- `tests/git_operations/test_verification.py` — add classes for each.

## WHAT

| Key | Probe | Format scope | Severity |
|---|---|---|---|
| `agent_reachable` | `_run([gpg-connect-agent, "/bye"], 5)` returncode 0. | openpgp / x509 only — absent for ssh. | warning |
| `allowed_signers` | `_get_config(repo, "gpg.ssh.allowedSignersFile")` set and `Path(...).is_file()`. | ssh only — absent for openpgp / x509. | warning |
| `verify_head` | `repo.head.is_valid()` first. If invalid → key absent. Otherwise `repo.git.verify_commit("HEAD")` via GitPython. Distinguish "HEAD unsigned" (skip silently) from other errors (`ok=False, severity="warning"`). | all formats | warning |

`gpg-connect-agent` is resolved via `shutil.which("gpg-connect-agent")` (not via
`gpg.program` — it's a separate binary). If unavailable, emit
`ok=False, severity="warning", value="not found"`.

`verify_head` semantics:
- `repo.head.is_valid()` False → key absent from result.
- `repo.git.verify_commit("HEAD")` succeeds → `ok=True, value="HEAD signature valid"`.
- `GitCommandError` whose stderr says HEAD has no signature
  (substring match: `"no signature"` or `"not signed"`) → key absent (opportunistic skip).
- Any other `GitCommandError` → `ok=False, severity="warning"`, `error=str(exc)[:500]`,
  value `"verify-commit failed"`. **Never** escalate to `severity="error"` per Decision #8.

## HOW

- Reuse `signing_binary_path` resolution from Step 5 only conceptually — `gpg-connect-agent`
  is its own binary. Resolve fresh via `shutil.which`.
- For `verify_head`, reopen `safe_repo_context(project_dir)` (cheap; `repo.head.is_valid()`
  is fast). Catch `GitCommandError` from `repo.git.verify_commit`.
- Only add `agent_reachable` to result for openpgp / x509 (absent for ssh).
- Only add `allowed_signers` for ssh (absent for openpgp / x509).
- `verify_head` is added for all formats (subject to the `is_valid()` skip).

## ALGORITHM

```
# agent_reachable (openpgp / x509 only)
if signing_format_resolved in ("openpgp", "x509"):
    agent = shutil.which("gpg-connect-agent")
    if agent is None:
        result["agent_reachable"] = CheckResult(
            ok=False, value="not found", severity="warning",
            error="gpg-connect-agent not on PATH",
            install_hint="...")
    else:
        proc = _run([agent, "/bye"], timeout=5)
        if proc.returncode == 0:
            result["agent_reachable"] = CheckResult(
                ok=True, value="reachable", severity="warning")
        else:
            result["agent_reachable"] = CheckResult(
                ok=False, value="unreachable", severity="warning",
                error=(proc.stderr or proc.stdout).strip()[:500])

# allowed_signers (ssh only)
if signing_format_resolved == "ssh":
    raw = _get_config(repo, "gpg.ssh.allowedSignersFile")
    if raw is None:
        result["allowed_signers"] = CheckResult(
            ok=False, value="not configured", severity="warning",
            error="gpg.ssh.allowedSignersFile is not set",
            install_hint="...")
    elif not Path(raw).is_file():
        result["allowed_signers"] = CheckResult(
            ok=False, value=f"file missing: {raw}", severity="warning",
            error=f"allowed signers file does not exist: {raw}")
    else:
        result["allowed_signers"] = CheckResult(
            ok=True, value=raw, severity="warning")

# verify_head (all formats)
try:
    with safe_repo_context(project_dir) as repo:
        if not repo.head.is_valid():
            pass  # key absent
        else:
            try:
                repo.git.verify_commit("HEAD")
                result["verify_head"] = CheckResult(
                    ok=True, value="HEAD signature valid", severity="warning")
            except GitCommandError as exc:
                stderr = (getattr(exc, "stderr", "") or "").lower()
                if "no signature" in stderr or "not signed" in stderr:
                    pass  # opportunistic skip — HEAD is unsigned
                else:
                    result["verify_head"] = CheckResult(
                        ok=False, value="verify-commit failed",
                        severity="warning",
                        error=str(exc)[:500])
except Exception as exc:
    result["verify_head"] = CheckResult(
        ok=False, value="verify-commit failed", severity="warning",
        error=str(exc)[:500])
```

## DATA

New result keys (only when intent detected, conditional on format):
- `agent_reachable` — present for openpgp & x509.
- `allowed_signers` — present for ssh.
- `verify_head` — present unless HEAD is invalid OR HEAD is unsigned.

`overall_ok` unaffected (all three are `severity="warning"`).

## Tests (written first)

Class `TestAgentReachable`:
- `test_agent_reachable_ok` — `gpg.format=openpgp`, `shutil.which("gpg-connect-agent")` ok, `_run` returncode 0 → `ok=True`, `severity="warning"`.
- `test_agent_unreachable` — `_run` returncode 2 → `ok=False`, error captured.
- `test_agent_binary_missing` — `shutil.which` None → `ok=False`, `value="not found"`.
- `test_agent_absent_for_ssh` — `gpg.format=ssh` → `"agent_reachable" not in result`.
- `test_agent_present_for_x509` — `gpg.format=x509` → key present.

Class `TestAllowedSigners`:
- `test_allowed_signers_ok` — `gpg.format=ssh`, config set, `Path.is_file` True → `ok=True`.
- `test_allowed_signers_unset` — config None → `ok=False`, value `"not configured"`.
- `test_allowed_signers_file_missing` — config set, `Path.is_file` False → `ok=False`, value contains `"file missing"`.
- `test_allowed_signers_absent_for_openpgp` — `gpg.format=openpgp` → key absent.
- `test_allowed_signers_absent_for_x509` — symmetric.

Class `TestVerifyHead`:
- `test_verify_head_ok_when_signed` — `repo.head.is_valid` True, `repo.git.verify_commit` returns ("ok") → `ok=True`, `severity="warning"`.
- `test_verify_head_absent_when_no_commits` — `repo.head.is_valid` False → `"verify_head" not in result`.
- `test_verify_head_absent_when_unsigned` — `verify_commit` raises `GitCommandError` with stderr `"error: no signature found"` → key absent.
- `test_verify_head_absent_when_not_signed_substring` — stderr `"object is not signed"` → key absent.
- `test_verify_head_warning_on_other_error` — `GitCommandError` with stderr `"fatal: bad object"` → `ok=False`, `severity="warning"` (NEVER `"error"`).
- `test_verify_head_severity_never_error` — even unrelated exceptions during repo open → `severity="warning"`.

Class `TestOverallOkUnaffectedByAuxiliaries`:
- `test_failing_agent_does_not_flip_overall_ok` — all error checks pass, `agent_reachable.ok=False` → `overall_ok=True`.

## Acceptance for this step

- `verify_head` is **never** `severity="error"` (Decision #8).
- `agent_reachable` is absent for ssh; `allowed_signers` is absent for openpgp/x509.
- `verify_head` is absent silently when HEAD is invalid or unsigned.
- `overall_ok` is unaffected by these three checks (all warning).
