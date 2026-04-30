# Step 4 — Tier 2 config-only checks: `signing_format`, `signing_key`

## LLM prompt

> Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_4.md`).
> Add the two config-only Tier 2 checks. These run only when Step 3's
> `signing_intent_detected` is True. Follow TDD. Run pylint, mypy, pytest,
> lint-imports, and tach. Produce one commit.

## WHERE

**Modified**

- `src/mcp_workspace/git_operations/verification.py` — append a Tier 2 block guarded by
  `if signing_intent_detected:`.
- `tests/git_operations/test_verification.py` — add classes for both checks.

## WHAT

Both checks added inside the `if signing_intent_detected:` block. When the gate is
False, neither key is present in the result (Decision #3).

| Key | Probe | Severity |
|---|---|---|
| `signing_format` | `gpg.format` config value. Allowed: `openpgp` (default if unset), `ssh`, `x509`. Anything else → error. | error |
| `signing_key` | `user.signingkey` set. Severity per Decision #10: **error** when `commit.gpgsign=true`; **warning** when only `tag.gpgsign` / `rebase.gpgSign` / `push.gpgSign` is true. | error / warning |

`signing_format` `value`:
- Unset → `"openpgp (default)"`, `ok=True`.
- `openpgp` / `ssh` / `x509` → that string, `ok=True`.
- Other → `f"unknown: {raw}"`, `ok=False`, `error=...`, `severity="error"`.

`signing_key` `value`:
- Set → `"configured"`, `ok=True`. **Do not log or echo the key value.**
- Unset → `"not set"`, `ok=False`. Severity follows the rule above.
- `install_hint` (when missing): `"Set user.signingkey via 'git config --global user.signingkey <ID>'"`.

The `signing_format` resolved value (one of `openpgp` / `ssh` / `x509`) is captured into
a function-local `signing_format_resolved: str` for downstream steps (5 & 7).

## HOW

- **Shared Tier 2 `safe_repo_context` block.** Step 4 **opens** a single
  `with safe_repo_context(project_dir) as repo:` block that spans **all Tier 2
  config reads** across Steps 4, 5, and 6. Steps 5 and 6 extend this same block —
  they must NOT reopen it. (`verify_head` in Step 6 is a deliberate exception: it
  needs a fresh context after Tier 2 config reads complete because it accesses
  `repo.head` and `repo.git.verify_commit`.)
  Note: this is a **separate** `safe_repo_context` block from the one used in
  Step 2 for `user_identity` — Tier 1 closes its block before Tier 2 opens this
  shared one.
- Reuse `_get_config(repo, "gpg.format")` and `_get_config(repo, "user.signingkey")`.
- The `flags_truthy` dict from Step 3 must remain in scope so Step 4 can consult
  `flags_truthy["commit.gpgsign"]` for the severity decision.
- For `signing_key`, set `severity="error"` only when `flags_truthy["commit.gpgsign"]`
  is True; otherwise `severity="warning"` even though `signing_key` is in Tier 2.

## ALGORITHM

```
if signing_intent_detected:
    with safe_repo_context(project_dir) as repo:
        raw_format = _get_config(repo, "gpg.format")
        signing_key = _get_config(repo, "user.signingkey")

    # signing_format
    if raw_format is None:
        signing_format_resolved = "openpgp"
        result["signing_format"] = CheckResult(ok=True, value="openpgp (default)",
                                               severity="error")
    elif raw_format in ("openpgp", "ssh", "x509"):
        signing_format_resolved = raw_format
        result["signing_format"] = CheckResult(ok=True, value=raw_format, severity="error")
    else:
        signing_format_resolved = "openpgp"  # fallback for downstream
        result["signing_format"] = CheckResult(
            ok=False, value=f"unknown: {raw_format}", severity="error",
            error=f"gpg.format must be openpgp, ssh, or x509 (got '{raw_format}')")

    # signing_key
    if signing_key is None:
        sev = "error" if flags_truthy["commit.gpgsign"] else "warning"
        result["signing_key"] = CheckResult(
            ok=False, value="not set", severity=sev,
            error="user.signingkey is not configured",
            install_hint="Set user.signingkey via "
                         "'git config --global user.signingkey <ID>'")
    else:
        result["signing_key"] = CheckResult(ok=True, value="configured",
                                             severity="error")
```

## DATA

New result keys (only when intent detected): `signing_format`, `signing_key`.
Function-local `signing_format_resolved: str` carried forward to Steps 5 / 7.

## Tests (written first)

Class `TestTier2GatedOnIntent`:
- `test_no_intent_means_keys_absent` — call with all signing flags unset; assert
  `"signing_format" not in result` and `"signing_key" not in result`.

Class `TestSigningFormat`:
- `test_unset_defaults_to_openpgp` — `gpg.format` unset, intent on → `value="openpgp (default)"`, `ok=True`.
- `test_explicit_openpgp` — `gpg.format=openpgp` → `ok=True`, value `"openpgp"`.
- `test_ssh_value` — `gpg.format=ssh` → `ok=True`.
- `test_x509_value` — `gpg.format=x509` → `ok=True`.
- `test_unknown_value` — `gpg.format=pgp` → `ok=False`, `severity="error"`, value contains `"unknown: pgp"`, error message present.

Class `TestSigningKeySeverity`:
- `test_missing_key_with_commit_gpgsign_is_error` — commit.gpgsign true, user.signingkey unset → `severity="error"`, `ok=False`. Combined with Step 1 framing, `result["overall_ok"]` is False.
- `test_missing_key_with_only_tag_gpgsign_is_warning` — only tag.gpgsign true, user.signingkey unset → `severity="warning"`, `ok=False`, `result["overall_ok"]` True.
- `test_missing_key_with_only_rebase_gpgsign_is_warning` — symmetric.
- `test_missing_key_with_only_push_gpgsign_is_warning` — symmetric.
- `test_key_present` — user.signingkey set → `ok=True`, severity error, `value="configured"`.
- `test_key_value_not_in_check_result` — patch `_get_config` to return a fake key id;
  assert that string is **not** present in the `value` field of `signing_key` and not in
  any logged `caplog.text`.

Class `TestOverallOkWithSigningSeverityRules`:
- `test_acceptance_only_tag_gpgsign_no_key_overall_ok` — exactly the acceptance criterion: only tag.gpgsign + missing key → `overall_ok=True`.

## Acceptance for this step

- A repo with `commit.gpgsign=true` and missing `user.signingkey` → `overall_ok=False`,
  `signing_key.severity="error"`.
- A repo with only `tag.gpgsign=true` and missing `user.signingkey` → `overall_ok=True`,
  `signing_key.severity="warning"`.
- A repo with `gpg.format=ssh` returns `signing_format.value="ssh"`, `ok=True`.
- A repo with no signing intent has neither `signing_format` nor `signing_key` in the result.
- The user's signing-key id never appears in the `CheckResult.value` field or in debug logs.
