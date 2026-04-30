# Step 3 — Tier 1 signing detection: `signing_intent`, `signing_consistency`

## LLM prompt

> Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_3.md`).
> Add the two Tier 1 signing-detection checks. This step also introduces the
> "intent detected?" gate that later steps use to decide whether to populate Tier 2.
> Follow TDD. Run pylint, mypy, pytest, lint-imports, and tach. Produce one commit.

## WHERE

**Modified**

- `src/mcp_workspace/git_operations/verification.py` — append two checks; introduce a
  local `signing_intent_detected: bool` for downstream steps.
- `tests/git_operations/test_verification.py` — extend with two new test classes.

## WHAT

| Key | Probe | Severity |
|---|---|---|
| `signing_intent` | OR of four flags read with `--type=bool`: `commit.gpgsign`, `tag.gpgsign`, `rebase.gpgSign`, `push.gpgSign`. Any `"true"` → intent detected. | warning |
| `signing_consistency` | When `commit.gpgsign=true`: warn if `rebase.gpgSign` unset; warn if `tag.gpgsign` unset. Single key per Decision #12 — if either sub-check fails, `ok=False` with concatenated `value` / `error`. | warning |

Use `_get_config(repo, key, "--type=bool")` for boolean reads; compare result to
`"true"` (Decision #14 — git canonicalises `yes`/`on`/`1`/`true`).

`signing_intent.value`:
- No flags true → `"not configured"`, `ok=True`.
- Any flag true → `"detected: <comma-separated flag names>"`, `ok=True`.
  Severity remains `warning` either way (informational).

`signing_consistency`:
- Only relevant when `commit.gpgsign=true`. If `commit.gpgsign` is false/unset, set
  `ok=True`, `value="not applicable"`.
- Both sub-checks pass: `ok=True`, `value="rebase ok; tag ok"`.
- One fails: `ok=False`, e.g. `value="rebase ok; tag.gpgsign unset"`,
  `error="tag.gpgsign unset → tags will be unsigned"`.
- Both fail: `ok=False`, `value="rebase.gpgSign unset; tag.gpgsign unset"`, combined error.

## HOW

- Add `signing_intent_detected = bool(...)` to the function-local scope. Subsequent
  steps gate Tier 2 on this flag.
- If `git_repo` is not OK, both signing checks emit `ok=False`, `severity="warning"`,
  `error="repository not accessible"`. (Don't block; just report unknown.)
- `install_hint` for `signing_intent`:
  `"Enable signing with 'git config --global commit.gpgsign true' (and set user.signingkey)."`

## ALGORITHM

```
flags_truthy = {}
if result["git_repo"]["ok"]:
    with safe_repo_context(project_dir) as repo:
        for flag in ("commit.gpgsign", "tag.gpgsign", "rebase.gpgSign", "push.gpgSign"):
            flags_truthy[flag] = (_get_config(repo, flag, "--type=bool") == "true")

signing_intent_detected = any(flags_truthy.values())

if not signing_intent_detected:
    result["signing_intent"] = CheckResult(ok=True, value="not configured",
                                            severity="warning", install_hint=...)
else:
    enabled = [k for k, v in flags_truthy.items() if v]
    result["signing_intent"] = CheckResult(ok=True,
                                            value=f"detected: {', '.join(enabled)}",
                                            severity="warning")

# signing_consistency
if not flags_truthy.get("commit.gpgsign"):
    result["signing_consistency"] = CheckResult(ok=True, value="not applicable",
                                                  severity="warning")
else:
    parts, errors = [], []
    rebase = "rebase ok" if flags_truthy["rebase.gpgSign"] else "rebase.gpgSign unset"
    tag    = "tag ok"    if flags_truthy["tag.gpgsign"]    else "tag.gpgsign unset"
    if not flags_truthy["rebase.gpgSign"]:
        errors.append("rebase.gpgSign unset → rebased commits unsigned on git < 2.36")
    if not flags_truthy["tag.gpgsign"]:
        errors.append("tag.gpgsign unset → tags will be unsigned")
    ok = not errors
    cr = CheckResult(ok=ok, value=f"{rebase}; {tag}", severity="warning")
    if errors:
        cr["error"] = "; ".join(errors)
    result["signing_consistency"] = cr
```

## DATA

New result keys: `signing_intent`, `signing_consistency`. `overall_ok` is unaffected
(both are `severity="warning"`).

## Tests (written first)

Class `TestSigningIntentNotConfigured`:
- `test_no_flags_set` — all four `_get_config` returns None → `value="not configured"`, `ok=True`.

Class `TestSigningIntentDetected`:
- `test_commit_gpgsign_true` — only commit.gpgsign true → `value` contains `"commit.gpgsign"`.
- `test_tag_only` — only tag.gpgsign true → `value` contains `"tag.gpgsign"`.
- `test_yes_value_recognised` — `_get_config(..., "--type=bool")` returns `"true"` (because git canonicalises `yes`) → detected. (Verifies we use `--type=bool`, not raw string match.)
- `test_extra_args_passed_to_config` — assert `_get_config` was called with `"--type=bool"` for each of the four flags.

Class `TestSigningConsistency`:
- `test_not_applicable_when_commit_off` — `commit.gpgsign` not true → `value="not applicable"`, `ok=True`.
- `test_both_sub_checks_pass` — commit + rebase + tag all true → `ok=True`, value contains `"rebase ok; tag ok"`.
- `test_rebase_unset_only` — commit + tag true, rebase unset → `ok=False`, value `"rebase.gpgSign unset; tag ok"`, error mentions rebase.
- `test_tag_unset_only` — commit + rebase true, tag unset → `ok=False`, value `"rebase ok; tag.gpgsign unset"`, error mentions tag.
- `test_both_unset` — commit true, rebase + tag unset → `ok=False`, both errors concatenated.
- `test_single_key_shape` — assert `result` does NOT have separate `signing_consistency_rebase` / `_tag` keys.

Class `TestRepoNotAccessibleSigningChecks`:
- `test_signing_intent_warning_when_no_repo` — `is_git_repository` False → both keys present, `ok=False`, `severity="warning"`.

Class `TestOverallOkUnaffectedByWarnings`:
- `test_signing_intent_failure_does_not_flip_overall_ok` — `git_repo` etc. OK, signing intent ok=False (warning) → `overall_ok=True`.

## Acceptance for this step

- A repo with no signing flags returns `signing_intent.value="not configured"`,
  `signing_consistency.value="not applicable"`, both `ok=True`.
- `commit.gpgsign=yes` (truthy alias) is recognised as detected.
- `signing_consistency` is a single key — never split into sub-keys.
- `overall_ok` is still `True` when only warnings fail.
- The function still returns no Tier 2 keys (those are added in Steps 4–6).
