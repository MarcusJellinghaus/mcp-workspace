# Step 8 — `perm_write` permission probe

## Prompt for LLM

> Read `pr_info/steps/summary.md` (especially "§7 `perm_write` is one coarse
> boolean"), then implement this step (`pr_info/steps/step_8.md`) only.
> Follow TDD: write the tests first, watch them fail, then implement.
> Use MCP tools for all file and check operations. One commit at the end.

Independent of steps 1–7.

---

## WHERE

- `src/mcp_workspace/github_operations/_permission_probes.py` — `_PROBE_KEYS`,
  new `_probe_write`, `run_permission_probes`, module docstring
- `src/mcp_workspace/github_operations/verification.py` — the section comment at
  line ~382 that says "6 fine-grained PAT permissions"
- `tests/github_operations/test_permission_probes.py`
- `tests/github_operations/test_verification.py`

## WHAT

```python
_PROBE_KEYS: tuple[str, ...] = (
    ...,                 # six existing read probes, order unchanged
    "perm_write",        # appended
)


def _probe_write(repo: Repository) -> CheckResult:
    """Report repository write access from repo.permissions.push."""
```

## HOW

- `perm_write` goes **into `_PROBE_KEYS`**, so it inherits the not-accessible
  placeholder path and the ordering guarantee for free. Append it — the six
  existing keys keep their order, and the order assertions in both test files
  derive from `_PROBE_KEYS`, so they need no edit.
- It gets its own small builder rather than `_run_probe`. `_run_probe` and
  `_classify_permission_response` are HTTP-status classifiers; this is a boolean
  attribute read with no URL and no status to classify.
- **`repo.permissions.push`, not `repo.permissions["push"]`.** PyGithub's
  `Permissions` is an object with a `.push` property (the issue text says
  subscript; that is wrong). An unpopulated attribute yields `None`, not a bool.
- Test `is True` / `is False` by identity and map anything else to "not checked".
  This is not defensive styling: `test_verification.py::TestPermissionProbeOverallOkUnaffected`
  asserts every `_PROBE_KEYS` entry has `ok is False` against a `Mock` repo,
  where `.permissions.push` is a truthy `Mock`. A `if push:` truthiness test
  would return `ok=True` and break it.
- `severity="warning"`, so a failure does not flip `overall_ok`.
- Reading `repo.permissions` costs no extra API call **provided** the attribute
  is populated on the cached repo payload; PyGithub lazily re-fetches when a
  field is unset, hence the try/except.
- Docstrings: the module docstring and `run_permission_probes`' docstring both
  say "six per-permission **read** probes" — both are now wrong.

## ALGORITHM

```
def _probe_write(repo):
    try: push = repo.permissions.push
    except Exception as e: return CheckResult(ok=False, value="not checked", severity="warning",
                                              error=f"could not read repository permissions: {e}")
    if push is True:  return CheckResult(ok=True,  value="OK", severity="warning")
    if push is False: return CheckResult(ok=False, value="no push access", severity="warning",
                                         error="token has no push access - GitHub write tools will fail")
    return CheckResult(ok=False, value="not checked", severity="warning",
                       error="repository permissions not reported")
```

In `run_permission_probes`, after `perm_statuses_read`:
`out["perm_write"] = _probe_write(repo)`.

## DATA

`CheckResult` — same shape as the six existing rows. Values: `"OK"`,
`"no push access"`, `"not checked"`.

One row, not six. `repo.permissions` gives `{admin, maintain, push, triage,
pull}` with no per-permission attribution and no relation to the fine-grained
permission names the six read probes use; synthesising
`perm_issues_write` / `perm_pull_requests_write` / … from the same boolean would
be five rows of false precision.

## Tests (TDD)

`tests/github_operations/test_permission_probes.py`:

1. Add `permissions.push = True` to the `mock_repo_full` fixture.
2. New `TestWriteProbe`: `push=True` → `ok=True`, `value="OK"`; `push=False` →
   `ok=False`, `value="no push access"`, error mentions push; `push=None` →
   `"not checked"`; `permissions` raising → `"not checked"` with the exception
   text.
3. Assert `severity == "warning"` on every branch.
4. Rename `TestSkipWhenUnreachable.test_six_placeholder_rows` →
   `test_placeholder_rows_for_all_keys` and fix its class docstring ("6
   placeholders").

`tests/github_operations/test_verification.py`:

5. Rename `test_six_placeholder_rows_no_pygithub_calls` →
   `test_placeholder_rows_no_pygithub_calls`; fix the "All 6 probe keys"
   comments and the `TestPermissionProbeKeyOrdering` /
   `TestPermissionProbeSkipWhenUnreachable` class docstrings.
6. Confirm `TestPermissionProbeOverallOkUnaffected` still passes unchanged —
   it is the guard described under HOW.

`SIMPLE_PROBE_PARAMS`, `URL_BY_KEY` and `_make_repo_with_probe_failure` are
read-probe-specific and stay as they are.

## Checks

`run_pylint_check`, `run_mypy_check`, `run_pytest_check`.

## Commit

`Add perm_write probe to verify_github`

## Before merge (not part of this commit)

Run the manual read-only-token check described in the summary and record the
result in the PR description. If `push` reports a false green for a read-only
token, drop the probe rather than ship it misleading.
