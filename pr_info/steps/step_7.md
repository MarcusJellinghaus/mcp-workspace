# Step 7 — Tier 3 opt-in deep probe: `actual_signature`

## LLM prompt

> Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_7.md`).
> Add the Tier 3 opt-in deep probe. This is the final step — after it,
> `verify_git` fully implements the issue. Follow TDD. Run pylint, mypy, pytest,
> lint-imports, and tach. Produce one commit.

## WHERE

**Modified**

- `src/mcp_workspace/git_operations/verification.py` — append the Tier 3 block guarded
  by `if actually_sign and signing_intent_detected:`.
- `tests/git_operations/test_verification.py` — add a Tier 3 class.

## WHAT

| Key | Probe | Severity |
|---|---|---|
| `actual_signature` | Only included when `actually_sign=True` and signing intent is detected. **openpgp**: `_run([gpg, "--clearsign", "--local-user", user.signingkey], 15)` with the fixed string `PROBE_PAYLOAD = "mcp-workspace verify_git probe"` written to stdin via the helper. **ssh / x509**: emit `ok=True, severity="warning", value="not implemented for ssh/x509"`. | error / warning |

The fixed payload is exposed as a module-level constant `PROBE_PAYLOAD` (Decision #15).

If `actually_sign=True` but `signing_intent_detected` is False, `actual_signature` is
**absent** (consistent with Decision #3 — Tier 2 absent → Tier 3 also absent).

## HOW

- Extend `_run` minimally: `actually_sign` needs stdin input, but the existing helper
  uses `stdin=subprocess.DEVNULL`. Add a tiny sibling `_run_with_input(args, *, input, timeout)`
  that does the same discipline (`capture_output=True`, `text=True`, `check=False`)
  but accepts an `input` string. Keep `_run` unchanged for everything else.
- Pre-conditions in order (any failure → emit a `CheckResult` with `ok=False, severity="error"`,
  do not invoke gpg):
  1. `signing_key` must have been OK in Step 4 — i.e. `result["signing_key"]["ok"]` True.
  2. `signing_binary_path` must be non-None.
- For ssh / x509, do not consult `signing_binary_path`; just emit the "not implemented"
  warning and return.
- `timeout=15` per Decision #6 (legitimate pinentry can take time).
- **Never log the produced signature.** Log only: returncode, truncated stderr (signature
  goes to stdout — discard it from logs entirely; do not log even truncated stdout for
  this probe). Log a fixed "signature produced" / "signature failed" string.

## ALGORITHM

```
PROBE_PAYLOAD = "mcp-workspace verify_git probe"

if actually_sign and signing_intent_detected:
    if signing_format_resolved in ("ssh", "x509"):
        result["actual_signature"] = CheckResult(
            ok=True, value="not implemented for ssh/x509",
            severity="warning")
    elif not result.get("signing_key", {}).get("ok"):
        result["actual_signature"] = CheckResult(
            ok=False, value="cannot probe: user.signingkey unavailable",
            severity="error")
    elif signing_binary_path is None:
        result["actual_signature"] = CheckResult(
            ok=False, value="cannot probe: gpg binary unavailable",
            severity="error")
    else:
        proc = _run_with_input(
            [signing_binary_path, "--clearsign", "--local-user", signing_key],
            input=PROBE_PAYLOAD, timeout=15)
        if proc.returncode == 0 and "BEGIN PGP SIGNED MESSAGE" in proc.stdout:
            result["actual_signature"] = CheckResult(
                ok=True, value="probe signed successfully", severity="error")
        else:
            result["actual_signature"] = CheckResult(
                ok=False, value="signing failed", severity="error",
                error=(proc.stderr or "").strip()[:500])

# overall_ok recomputed at the very end of verify_git()
```

## DATA

New result key: `actual_signature` (only when `actually_sign=True` and
`signing_intent_detected`). Module-level constant: `PROBE_PAYLOAD`.

## Tests (written first)

Class `TestActuallySignDefault`:
- `test_default_no_actual_signature_key` — `verify_git(tmp_path)` (no `actually_sign`) → `"actual_signature" not in result`.
- `test_default_does_not_invoke_signing_subprocess` — patch the helpers; assert no `_run_with_input` call occurred.

Class `TestActuallySignOpenPGP`:
- `test_signing_succeeds` — full happy-path mock + `actually_sign=True` + `_run_with_input` returncode 0, stdout contains `"-----BEGIN PGP SIGNED MESSAGE-----\n... -----BEGIN PGP SIGNATURE-----\n... -----END PGP SIGNATURE-----"` → `ok=True, severity="error"`, value `"probe signed successfully"`.
- `test_fixed_probe_string_is_used` — capture the `input` argument passed to `_run_with_input`; assert it equals `"mcp-workspace verify_git probe"`. (Decision #15.)
- `test_signing_failure_pinentry_cancelled` — `_run_with_input` returncode 2, stderr `"gpg: signing failed: No pinentry"` → `ok=False, severity="error"`, error contains the stderr.
- `test_signing_failure_no_secret_key` — `_run_with_input` returncode 2, stderr `"No secret key"` → `ok=False`, error captured.
- `test_signed_payload_not_logged` — `caplog.set_level(DEBUG)`, run with `_run_with_input` returning a fake clearsigned blob; assert that the fake signature substring (e.g. `"FAKEBASE64SIG"`) does NOT appear in `caplog.text`. (Decision #11.)

Class `TestActuallySignSSHandX509`:
- `test_ssh_returns_not_implemented_warning` — `gpg.format=ssh`, `actually_sign=True` → `ok=True, severity="warning", value="not implemented for ssh/x509"`. (Decision #7.)
- `test_x509_returns_not_implemented_warning` — symmetric.
- `test_ssh_does_not_invoke_subprocess` — assert `_run_with_input` was NOT called.

Class `TestActuallySignPreconditions`:
- `test_no_intent_no_actual_signature` — `actually_sign=True` but no signing intent → key absent.
- `test_missing_signing_key_emits_error` — intent on, but `user.signingkey` unset → `actual_signature.ok=False, severity="error", value` mentions `"unavailable"`.
- `test_unavailable_signing_binary_emits_error` — intent on, but `signing_binary` failed → `actual_signature.ok=False, severity="error"`.

Class `TestActuallySignNeverPromptsByDefault`:
- `test_default_does_not_prompt` — explicit assertion that `actually_sign=False` (default) → `_run_with_input` is not called and `subprocess.run` is not called with any pinentry-capable command. (Reinforces "never prompts by default".)

## Acceptance for this step

- `verify_git(tmp_path)` (default) → `"actual_signature" not in result` and no signing
  subprocess invoked.
- `verify_git(tmp_path, actually_sign=True)` with openpgp + valid key + reachable
  binary → invokes the gpg subprocess with the literal payload
  `"mcp-workspace verify_git probe"`.
- `verify_git(tmp_path, actually_sign=True)` with `gpg.format=ssh` or `gpg.format=x509`
  returns `actual_signature` with `ok=True, severity="warning",
  value="not implemented for ssh/x509"`.
- The signed-payload bytes never appear in any debug log.
- All issue acceptance criteria are met:
  - "no signing configured" → `overall_ok=True`, all Tier 2 keys absent.
  - `commit.gpgsign=true` + missing `user.signingkey` → `overall_ok=False`,
    `signing_key.severity="error"`.
  - Only `tag.gpgsign=true` + missing key → `overall_ok=True`,
    `signing_key.severity="warning"`.
  - `commit.gpgsign=true` + `gpg.program` missing-file → `overall_ok=False`,
    `signing_binary.severity="error"`.
  - `commit.gpgsign = yes` recognised as having intent.
  - `signing_consistency` is single-key with concatenated value/error.
  - Function never prompts when `actually_sign=False`.
  - `actually_sign=True` for openpgp uses the fixed probe string.
  - Debug logs never include key IDs / fingerprints / signed payload.
