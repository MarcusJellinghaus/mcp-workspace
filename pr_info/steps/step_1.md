# Step 1 — `ok: bool | None` and `ok=None` placeholders

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_1.md`. Use TDD: update the tests first, then the code. Run pylint, pytest (`-n auto`) and mypy until all three pass, then produce one commit.

## WHERE

- `src/mcp_workspace/github_operations/_types.py`
- `src/mcp_workspace/github_operations/verification.py`
- `src/mcp_workspace/github_operations/_permission_probes.py`
- `tests/github_operations/test_verification.py`
- `tests/github_operations/test_permission_probes.py`

## WHAT

- `_types.py`: `CheckResult.ok: bool | None`. Extend the docstring: `None` means the check could not be verified.
- `verification.py`: add a module constant and a helper.

```python
_PROTECTION_KEYS: tuple[str, ...] = (
    "branch_protection", "ci_checks_required", "strict_mode", "force_push", "branch_deletion",
)

def _protection_rows(ok: bool | None, value: str, error: str) -> dict[str, CheckResult]:
    """Build one identical warning row per branch-protection key."""
```

## HOW

- `verification.py`: replace the three duplicated five-key loops (lines 234–283) with `result.update(_protection_rows(...))`.
  - The repo-inaccessible call passes `ok=None`, `"unknown"`, `"repository not accessible"`.
  - The two exception branches keep today's behaviour: `ok=False`, `"not configured"`, and the same `error`.
- `verification.py`: the `auto_delete_branches` placeholder for an inaccessible repo becomes `ok=None`.
- `_permission_probes.py`: these rows become `ok=None`:
  - the six `run_permission_probes` placeholders when `repo is None`
  - `_probe_statuses` when the commit lookup fails
  - `_probe_administration` when the branch lookup fails
- `repo_accessible` stays `ok=False, severity="error"`.

## ALGORITHM

```
_protection_rows:
    return {k: CheckResult(ok=ok, value=value, severity="warning", error=error)
            for k in _PROTECTION_KEYS}
```

## DATA

The result dict keeps the same keys in the same order. Only `ok` changes on placeholder rows.

## Tests (write first)

`test_verification.py`:
- `TestBranchProtectionWhenRepoNotAccessible`: all five rows `ok is None`, value `"unknown"`, error present.
- `TestAutoDeleteBranches.test_repo_not_accessible`: `ok is None`.
- `TestPermissionProbeSkipWhenUnreachable` (around line 1218): `ok is None`.
- New `TestOverallOkWithUnverifiableRows`: with the repo inaccessible, assert that `ok is None` rows are present and that `overall_ok` equals `all()` over the error-severity rows. `repo_accessible` is an error row, so `overall_ok` is `False` here. The test proves the `None` warning rows don't take part.
  - Add a second case using `_patch_all_ok` with a patched `run_permission_probes` that returns `ok=None` rows, and assert `overall_ok is True`.

`test_permission_probes.py`:
- `TestSkipWhenUnreachable.test_six_placeholder_rows`: `ok is None`.
- `TestStatusesTwoCallAttribution.test_get_commit_raises_skips_classifier`: `ok is None`.
- `TestAdministrationTwoCallAttribution.test_get_branch_raises_skips_classifier`: `ok is None`.
