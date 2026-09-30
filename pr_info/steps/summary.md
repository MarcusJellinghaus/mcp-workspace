# Summary — #301: report "not verifiable" (ok=None) when branch protection cannot be read

## Goal

`verify_github` sets `ok=False` only for a verified negative. Anything it could not verify gets `ok=None`, which mcp_coder renders as `[WARN]` without the `({error})` suffix. The main fix: a 403 from `get_protection()` no longer claims "not configured".

## Architectural / design changes

1. **`CheckResult.ok` is `bool | None`.** This applies only to the GitHub `CheckResult` in `github_operations/_types.py`. `git_operations/_signing_helpers.py` has its own and stays `bool`.
   - `True`: verified positive.
   - `False`: verified negative.
   - `None`: could not verify.

   `overall_ok` still counts only `severity == "error"` rows. Every affected row is `warning`, so the exit code is unchanged.

2. **Branch protection is fetched once.**
   - `verify_github` calls a new `_fetch_protection(manager, repo)`. It runs `get_default_branch`, `get_branch` and `get_protection` once each, and returns a `ProtectionOutcome(branch, stage, protection, exception)`.
   - Two consumers classify that one outcome: the branch-protection block and the Administration probe.
   - `run_permission_probes` takes it as a required, keyword-only `protection_outcome`. It is `None` when the repo is inaccessible.
   - The Administration probe no longer makes API calls.

3. **Branch-protection rows follow a fixed table.**
   - A `Branch not protected` 404 is the only verified negative: `ok=False`, `not configured`.
   - 401 and 403 get dedicated `not verifiable — …` texts.
   - Every other failure is `not verifiable — <short reason>`.
   - One helper, `_protection_rows`, builds all five rows, so they always agree.
   - No raw JSON reaches `value` or `error`. The full response body is logged at debug level.

4. **Probe wording.**
   - The hardcoded "blocked by org policy (403)" is replaced by neutral 403 text in the shared classifier.
   - The `admin_404` special case is removed.
   - A `Branch not protected` 404 makes the Administration probe `ok=True`, because GitHub answered, so the token can read the endpoint.
   - The probe's exception handling moves into `_classify_exception`, shared by `_run_probe` and the Administration probe.

5. **Unchanged, deliberately.**
   - Administration probe on 403: stays `ok=False`.
   - Probe network errors, 5xx and ambiguous 404s: stay `ok=False`.
   - The result dict's keys, their order, and the row shapes.

## Branch-protection outcome table (all five keys agree)

| Outcome | `ok` | `branch_protection` value | `error` |
|---|---|---|---|
| 200 | `True` | `<branch> protected` (children as today) | — |
| 404 `Branch not protected` | `False` | `not configured` | `no branch protection` |
| 401 | `None` | `not verifiable — token rejected (401)` | `<stage> failed: <reason>` |
| 403 | `None` | `not verifiable — token lacks Administration: Read` | `<stage> failed: <reason>` |
| `get_branch` fails / anything else | `None` | `not verifiable — <reason>` | `<stage> failed: <reason>` |
| repo inaccessible | `None` | `unknown` | `repository not accessible` |

In the table:

- `<reason>` is `HTTP <status>`, plus `: <message>` when GitHub's `message` is a string of 100 characters or fewer. For a non-GitHub exception, it is the exception's type name.
- `<stage>` is `get_branch` or `get_protection`.

The 401 and 403 texts apply only when the failure comes from `get_protection`.

## Files

| File | Change |
|---|---|
| `src/mcp_workspace/github_operations/_types.py` | `ok: bool \| None`; add `ProtectionOutcome` |
| `src/mcp_workspace/github_operations/verification.py` | `_protection_rows`, `_fetch_protection`, `_short_reason`, `_classify_protection_failure`; `ok=None` placeholders |
| `src/mcp_workspace/github_operations/_permission_probes.py` | 403 wording, drop `admin_404`, `_is_branch_not_protected`, `_classify_exception`, outcome-based `_probe_administration`, `protection_outcome` kwarg, `ok=None` for `not checked` |
| `tests/github_operations/test_permission_probes.py` | update listed tests; outcome fixtures; admin-probe outcome tests |
| `tests/github_operations/test_verification.py` | update listed tests; parametrized outcome table; single-fetch and `overall_ok` regression tests |

No new modules or folders.

## Steps

1. [step_1.md](step_1.md): `ok: bool | None`, `_protection_rows`, `ok=None` for every `not checked` or `unknown` placeholder.
2. [step_2.md](step_2.md): probe classifier wording (403 text, drop `admin_404`).
3. [step_3.md](step_3.md): single protection fetch (`ProtectionOutcome`); the Administration probe classifies the shared outcome.
4. [step_4.md](step_4.md): branch-protection outcome table (`not verifiable`, no raw JSON).
