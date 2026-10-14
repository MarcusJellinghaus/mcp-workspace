# Step 2 — `dependabot_alerts` probe via low-level `requestJson`

See [summary.md](./summary.md) for overall architecture and context.

## Goal

Add `_probe_dependabot_alerts(repo)`, the one function in this module that
talks to PyGithub. It must bypass `Repository.get_vulnerability_alert()`
and call `repo.requester.requestJson(...)` directly (see summary.md and
issue #314 for why `get_vulnerability_alert()` cannot be reused — it
collapses 404/403/etc. into a bare `False`). TDD: extend the test file
with the new probe's tests first, confirm they fail, then implement.

## WHERE

- Modify `src/mcp_workspace/github_operations/_security_probes.py`
  (add one function + one import)
- Modify `tests/github_operations/test_security_probes.py` (add tests)

## WHAT

```python
def _probe_dependabot_alerts(repo: Repository) -> CheckResult: ...
```

## HOW

- Add imports: `from github import Consts` and
  `from github.Repository import Repository` (the latter for the type hint
  only — mirrors `_permission_probes.py`'s existing import style).
- Calls `repo.requester.requestJson("GET", f"{repo.url}/vulnerability-alerts",
  headers={"Accept": Consts.vulnerabilityAlertsPreview})` — the exact call
  `Repository.get_vulnerability_alert()` makes internally, just without
  going through its `status == 204` collapse.
- `repo.requester` is PyGithub's public property (present since the
  project's floor `PyGithub>=2.7.0`) — not a private-attribute reach, so no
  `# pylint: disable=protected-access` needed.
- Delegates status classification to `_classify_vulnerability_alerts` from
  Step 1 — do not duplicate the 204/404 branching here.

## ALGORITHM

```
try:
    status, _, _ = repo.requester.requestJson("GET", url, headers=...)
except Exception as exc:
    return ok=None, value="not accessible", error=f"network error: {exc}"
return _classify_vulnerability_alerts(status)
```

The `try/except` here is for genuine transport failures (connection errors),
not HTTP error statuses — `requestJson()` never raises for an HTTP status,
per the issue's PyGithub-source analysis. Use a broad
`except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-exception-caught`,
matching the existing style in `base_manager.py` / `verification.py`.

## DATA

Returns `CheckResult`, `severity="warning"` always (via the Step 1
classifier or the network-error branch above).

## Tests to add (`test_security_probes.py`)

Build a `Mock()` repo with `repo.url = "https://api.github.com/repos/owner/repo"`
and `repo.requester.requestJson` configured per case:

- `return_value=(204, {}, "")` -> result `ok=True`, `"enabled"`.
- `return_value=(404, {}, "")` -> result `ok=False`, `"disabled"`.
- `return_value=(403, {}, "")` -> result `ok=None`, `"not accessible"`,
  `error` contains `"403"`.
- `side_effect=ConnectionError("boom")` -> result `ok=None`,
  `"not accessible"`, `error` contains `"boom"`.
- Assert `repo.requester.requestJson` was called with method `"GET"` and
  the `Accept` header set to `Consts.vulnerabilityAlertsPreview` (assert on
  `call_args`), confirming `get_vulnerability_alert()` itself is never
  called (`repo.get_vulnerability_alert.assert_not_called()`).

## Precondition check

This step assumes `github.Consts.vulnerabilityAlertsPreview` and
`Repository.requester` exist in the installed PyGithub version (already
confirmed analytically against the project's floor dependency in issue
#314's discussion). If importing `Consts` or accessing `.requester` on a
real `Repository` instance raises `AttributeError`/`ImportError` during
implementation, write one line to `pr_info/.blocked.txt` and stop.

## Commit

One commit. Suggested message:
`test+feat(security_probes): add dependabot_alerts probe via requestJson`

## LLM prompt for this step

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_2.md` in this
> repo. Step 1 is already implemented and committed. Implement exactly what
> Step 2 describes: add the new tests listed in Step 2 to
> `tests/github_operations/test_security_probes.py` first, confirm they
> fail, then add `_probe_dependabot_alerts` to `_security_probes.py` per
> Step 2's ALGORITHM, reusing `_classify_vulnerability_alerts` from Step 1.
> Do not implement `verify_github_security` or touch `__init__.py` — that's
> Steps 3-4. If the precondition check in Step 2 fails, write one line to
> `pr_info/.blocked.txt` and stop. Run
> `mcp__mcp-tools-py__run_pylint_check`,
> `mcp__mcp-tools-py__run_pytest_check` (with `extra_args: ["-n", "auto"]`),
> and `mcp__mcp-tools-py__run_mypy_check`; fix anything they flag. Run
> `mcp__mcp-tools-py__run_format_code`, then make exactly one commit.
