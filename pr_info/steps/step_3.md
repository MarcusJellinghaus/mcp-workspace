# Step 3 — `verify_github_security()` orchestration

See [summary.md](./summary.md) for overall architecture and context.

## Goal

Add the public entry point `verify_github_security(project_dir)` that
resolves its own repo (independent of `verify_github()`) and assembles the
four `CheckResult`s from Steps 1-2. TDD: extend the test file with the
orchestration tests first, confirm they fail, then implement.

## WHERE

- Modify `src/mcp_workspace/github_operations/_security_probes.py`
  (add one function + three imports)
- Modify `tests/github_operations/test_security_probes.py` (add tests)

## WHAT

```python
def verify_github_security(project_dir: Path) -> dict[str, CheckResult]: ...
```

## HOW

- Add imports: `import logging`, `from pathlib import Path`, and
  `from mcp_workspace.github_operations.base_manager import BaseGitHubManager`.
  Add a module-level `logger = logging.getLogger(__name__)`, matching
  `verification.py` / `base_manager.py`.
- Builds its own `BaseGitHubManager(project_dir=project_dir)` and calls
  `manager._get_repository()` — same two calls `verify_github()` makes,
  but resolved independently here, not threaded through. This mirrors
  `_permission_probes.py`'s existing shape and is the accepted "second
  auth round-trip" from mcp_coder#1180's Decisions table.
- On any failure resolving the manager or the repo, return the 4-key
  placeholder dict and issue **no further PyGithub calls** — same contract
  as `run_permission_probes`'s skip path in `_permission_probes.py`.
- On success, reads `repo.security_and_analysis` once and passes each
  sub-field (or `None`) to `_classify_security_feature` from Step 1 — three
  explicit lines, not a loop over attribute names (exactly three fixed
  fields; explicit attribute access is clearer and more mypy-friendly than
  `getattr` by string name).
- The `except Exception as exc:` around `BaseGitHubManager`/`_get_repository`
  construction only guards the constructor (`_get_repository()` itself never
  raises — it already catches and logs internally). Log the exception via
  `logger.debug` and mark it with
  `# noqa: BLE001  # pylint: disable=broad-exception-caught`, matching the
  existing style in `base_manager.py` / `verification.py` (and Step 2's
  network-error branch).

## ALGORITHM

```
try:
    manager = BaseGitHubManager(project_dir=project_dir)
    repo = manager._get_repository()
except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-exception-caught
    logger.debug("verify_github_security manager/repo resolution failed: %s", exc)
    repo = None

if repo is None:
    return {k: (ok=None, value="not checked", error="repository not accessible")
            for k in _SECURITY_KEYS}

sa = repo.security_and_analysis
return {
    "dependabot_alerts": _probe_dependabot_alerts(repo),
    "dependabot_security_updates": _classify_security_feature(
        None if sa is None else sa.dependabot_security_updates, "Dependabot security updates"),
    "secret_scanning": _classify_security_feature(
        None if sa is None else sa.secret_scanning, "Secret scanning"),
    "secret_scanning_push_protection": _classify_security_feature(
        None if sa is None else sa.secret_scanning_push_protection, "Secret scanning push protection"),
}
```

## DATA

Returns `dict[str, CheckResult]` with exactly the 4 keys in
`_SECURITY_KEYS` order, each `severity="warning"`.

## Tests to add (`test_security_probes.py`)

Follow `test_verification.py`'s existing mocking pattern: patch
`BaseGitHubManager` where it is imported in the module under test —
`patch("mcp_workspace.github_operations._security_probes.BaseGitHubManager")`.

- **Repo not accessible** (`mock_manager._get_repository.return_value = None`):
  result has exactly the 4 `_SECURITY_KEYS`, each `ok=None`,
  `value="not checked"`, `error="repository not accessible"`.
- **Manager construction raises** (`mock_mgr_cls.side_effect = ValueError("no token")`):
  same 4-row placeholder result.
- **`security_and_analysis is None`** (repo mock with
  `security_and_analysis=None`, `requester.requestJson.return_value=(204, {}, "")`):
  `dependabot_alerts` is `ok=True`; the other 3 keys are all `ok=None`,
  `"not accessible"`.
- **All-enabled** (repo mock with `security_and_analysis` whose 3 sub-fields
  are each `Mock(status="enabled")`, `requester.requestJson.return_value=(204, {}, "")`):
  all 4 keys `ok=True`.
- **Mixed** (one sub-field `Mock(status="disabled")`, alerts returns 404):
  confirms each key is classified independently.
- **Key order**: `tuple(result.keys()) == _SECURITY_KEYS` for the
  all-enabled case.

## Precondition check

None beyond Steps 1-2 already being in place — proceed directly to
implementation.

## Commit

One commit. Suggested message:
`test+feat(security_probes): add verify_github_security orchestration`

## LLM prompt for this step

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_3.md` in this
> repo. Steps 1-2 are already implemented and committed. Implement exactly
> what Step 3 describes: add the new tests listed in Step 3 to
> `tests/github_operations/test_security_probes.py` first (mocking
> `BaseGitHubManager` the way `tests/github_operations/test_verification.py`
> already does for `verify_github`), confirm they fail, then add
> `verify_github_security` to `_security_probes.py` per Step 3's ALGORITHM,
> reusing `_probe_dependabot_alerts` and `_classify_security_feature` from
> Steps 1-2. Do not modify `__init__.py` or
> `tests/github_operations/test_package_exports.py` — that's Step 4. Run
> `mcp__mcp-tools-py__run_pylint_check`,
> `mcp__mcp-tools-py__run_pytest_check` (with `extra_args: ["-n", "auto"]`),
> and `mcp__mcp-tools-py__run_mypy_check`; fix anything they flag. Run
> `mcp__mcp-tools-py__run_format_code`, then make exactly one commit.
