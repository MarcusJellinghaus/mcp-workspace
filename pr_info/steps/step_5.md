# Step 5 — Tier 2 binary checks: `signing_binary`, `signing_key_accessible`

## LLM prompt

> Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_5.md`).
> Add the two binary-probe Tier 2 checks. They consume `signing_format_resolved`
> from Step 4. Follow TDD. Run pylint, mypy, pytest, lint-imports, and tach. Produce
> one commit.

## WHERE

**Modified**

- `src/mcp_workspace/git_operations/verification.py` — append two checks inside the
  Tier 2 block.
- `tests/git_operations/test_verification.py` — add classes for both checks and for
  the `gpg.program` precedence behaviour (Decision #13).

## WHAT

Both checks gated on `signing_intent_detected`. Each respects `signing_format_resolved`.

| Key | Probe (per format) | Severity |
|---|---|---|
| `signing_binary` | openpgp: `gpg.program` config first; if set but file missing → **error, no fallback** (Decision #13). If unset → `shutil.which("gpg")`. Then `_run([resolved, "--version"], 5)`. ssh: `shutil.which("ssh-keygen")` + `--version`. x509: `shutil.which("gpgsm")` + `--version`. | error |
| `signing_key_accessible` | openpgp: `_run([gpg, "--list-secret-keys", user.signingkey], 5)` returns non-empty match. ssh: `user.signingkey` resolves to a readable file (`Path(...).is_file()`) or matches a loaded key (file path branch only — agent branch deferred). x509: `_run([gpgsm, "--list-secret-keys", user.signingkey], 5)`. | error |

`install_hint`s:
- `signing_binary` (openpgp): `"Install Gpg4win (Windows) or 'gpg' (Linux/Mac), or set gpg.format=ssh"`.
- `signing_binary` (ssh): `"Install OpenSSH ≥ 8.0 (provides ssh-keygen)"`.
- `signing_binary` (x509): `"Install gpgsm (part of GnuPG) or set gpg.format=openpgp"`.

The resolved binary path is carried into a function-local `signing_binary_path: Optional[str]`
for Steps 6 (`agent_reachable`) and 7 (`actual_signature`).

## HOW

- Resolve `gpg.program` via `_get_config(repo, "gpg.program")` (only for openpgp).
- For "set but missing": `if raw and not Path(raw).is_file()` → `signing_binary` is
  `ok=False, severity="error", value="configured but missing: <raw>"`,
  `error=f"gpg.program points to non-existent file: {raw}"`, **and**
  `signing_binary_path = None` so downstream checks know not to probe further.
- For "set and present": resolved = `raw`. Log via `logger.debug` (path is OK to log).
- For "unset": resolved = `shutil.which("gpg")` (or `ssh-keygen` / `gpgsm`).
- If `user.signingkey` is unset (Step 4 already reported), skip
  `signing_key_accessible` cleanly — emit `ok=False, severity="error",
  value="cannot probe: user.signingkey not set", error="..."`. (Still present —
  Tier 2 keys are absent only when the entire signing intent is undetected.)
- Never include the key id or the binary's stdout in the `CheckResult.value` for
  `signing_key_accessible`. Use `value="found"` / `value="not found"`.

## ALGORITHM

```
# signing_binary (still inside the `if signing_intent_detected:` block)
signing_binary_path = None

if signing_format_resolved == "openpgp":
    raw = _get_config(repo, "gpg.program")
    if raw is not None:
        if Path(raw).is_file():
            signing_binary_path = raw
        else:
            result["signing_binary"] = CheckResult(
                ok=False, value=f"configured but missing: {raw}",
                severity="error",
                error=f"gpg.program points to non-existent file: {raw}",
                install_hint="...")
            # signing_binary_path stays None
    if signing_binary_path is None and "signing_binary" not in result:
        signing_binary_path = shutil.which("gpg")
elif signing_format_resolved == "ssh":
    signing_binary_path = shutil.which("ssh-keygen")
elif signing_format_resolved == "x509":
    signing_binary_path = shutil.which("gpgsm")

if "signing_binary" not in result:
    if signing_binary_path is None:
        result["signing_binary"] = CheckResult(
            ok=False, value="not found", severity="error",
            error=f"binary for {signing_format_resolved} not on PATH",
            install_hint="...")
    else:
        proc = _run([signing_binary_path, "--version"], timeout=5)
        if proc.returncode == 0:
            result["signing_binary"] = CheckResult(
                ok=True,
                value=(proc.stdout.splitlines() or [""])[0].strip()[:200],
                severity="error")
        else:
            result["signing_binary"] = CheckResult(
                ok=False, value="not runnable", severity="error",
                error=(proc.stderr or "").strip()[:500])
            signing_binary_path = None  # don't try to use a broken binary downstream

# signing_key_accessible
if signing_key is None:
    result["signing_key_accessible"] = CheckResult(
        ok=False, value="cannot probe: user.signingkey not set",
        severity="error", error="user.signingkey unset")
elif signing_binary_path is None:
    result["signing_key_accessible"] = CheckResult(
        ok=False, value="cannot probe: signing binary unavailable",
        severity="error", error="signing_binary failed")
elif signing_format_resolved == "openpgp":
    proc = _run([signing_binary_path, "--list-secret-keys", signing_key], timeout=5)
    ok = proc.returncode == 0 and bool(proc.stdout.strip())
    result["signing_key_accessible"] = (
        CheckResult(ok=True, value="found", severity="error")
        if ok else
        CheckResult(ok=False, value="not found", severity="error",
                    error=(proc.stderr or proc.stdout).strip()[:500] or "no match"))
elif signing_format_resolved == "ssh":
    p = Path(signing_key)
    result["signing_key_accessible"] = (
        CheckResult(ok=True, value="found", severity="error")
        if p.is_file()
        else CheckResult(ok=False, value="not found", severity="error",
                          error=f"ssh key file not found: {signing_key}"))
elif signing_format_resolved == "x509":
    proc = _run([signing_binary_path, "--list-secret-keys", signing_key], timeout=5)
    ok = proc.returncode == 0 and bool(proc.stdout.strip())
    result["signing_key_accessible"] = (
        CheckResult(ok=True, value="found", severity="error")
        if ok else
        CheckResult(ok=False, value="not found", severity="error",
                    error=(proc.stderr or proc.stdout).strip()[:500] or "no match"))
```

## DATA

New result keys (only when intent detected): `signing_binary`, `signing_key_accessible`.
Function-local `signing_binary_path: Optional[str]` carried into later steps.

## Tests (written first)

Class `TestSigningBinaryOpenPGP`:
- `test_gpg_program_set_and_present` — `gpg.program=/opt/gpg/gpg`, `Path.is_file` True, `_run` returncode 0 → `ok=True`, value contains `"gpg"`.
- `test_gpg_program_set_but_missing_is_error_no_fallback` — `gpg.program=/missing/gpg`, `Path.is_file` False, `shutil.which("gpg")` returns `/usr/bin/gpg` → `signing_binary.ok=False`, `severity="error"`, value contains `"configured but missing"`. Crucially, assert that `_run` was NOT called and `shutil.which` was either not called or its result was ignored.
- `test_gpg_program_unset_uses_path` — `gpg.program` unset, `shutil.which` returns `/usr/bin/gpg`, `_run` ok → `ok=True`.
- `test_gpg_not_on_path` — both `gpg.program` unset and `shutil.which` returns None → `ok=False`, `value="not found"`.
- `test_gpg_runnable_failure` — `shutil.which` ok, `_run` returncode 2 → `ok=False`, error from stderr.

Class `TestSigningBinarySSH`:
- `test_ssh_keygen_found` — `gpg.format=ssh`, `shutil.which("ssh-keygen")` ok, `_run` ok → `ok=True`.
- `test_ssh_keygen_not_found` — `shutil.which("ssh-keygen")` returns None → `ok=False`.

Class `TestSigningBinaryX509`:
- `test_gpgsm_found` — symmetric to ssh with `gpgsm`.
- `test_gpgsm_not_found` — symmetric.

Class `TestSigningKeyAccessible`:
- `test_openpgp_key_found` — `_run` returncode 0 with non-empty stdout → `ok=True`, value `"found"`.
- `test_openpgp_key_not_found` — `_run` returncode 2 → `ok=False`, value `"not found"`.
- `test_ssh_key_file_present` — `gpg.format=ssh`, `user.signingkey=/home/user/.ssh/id`, `Path.is_file` True → `ok=True`.
- `test_ssh_key_file_missing` — `Path.is_file` False → `ok=False`, error contains the path.
- `test_x509_key_found` — symmetric to openpgp via gpgsm.
- `test_skipped_when_signingkey_unset` — Step 4 set `signing_key.ok=False`; this check still emits `value="cannot probe: user.signingkey not set"`, `ok=False`.
- `test_skipped_when_binary_unavailable` — `signing_binary.ok=False`; this check emits `value="cannot probe: signing binary unavailable"`.
- `test_key_id_not_logged` — `caplog.set_level(DEBUG)`, run with a fake key id `"ABC123KEY"`; assert the literal string `"ABC123KEY"` does NOT appear anywhere in `caplog.text`. (Sensitive-data redaction per Decision #11.)

## Acceptance for this step

- `commit.gpgsign=true`, `gpg.program` set to a missing file → `signing_binary.severity="error"`,
  `overall_ok=False`. (Acceptance criterion from issue.)
- `gpg.program` is honoured with precedence over `shutil.which("gpg")`.
- ssh and x509 paths use `ssh-keygen` and `gpgsm` respectively.
- The user's signing key id never appears in any logged output (DEBUG level).
