# Step 1 — Pure classifier functions

See [summary.md](./summary.md) for overall architecture and context.

## Goal

Create the new module `_security_probes.py` with its two pure,
side-effect-free classifier functions and the shared key tuple. No
PyGithub/network calls yet — those come in later steps. TDD: write the test
file first, run it (red, `ModuleNotFoundError`/`ImportError`), then add the
implementation (green).

## WHERE

- Create `src/mcp_workspace/github_operations/_security_probes.py`
- Create `tests/github_operations/test_security_probes.py`

## WHAT

```python
# _security_probes.py
_SECURITY_KEYS: tuple[str, ...] = (
    "dependabot_alerts",
    "dependabot_security_updates",
    "secret_scanning",
    "secret_scanning_push_protection",
)

def _classify_vulnerability_alerts(status: int) -> CheckResult: ...
def _classify_security_feature(feature: Any, display_name: str) -> CheckResult: ...
```

## HOW

- Module docstring explaining this is the companion to
  `_permission_probes.py`, reusing the tri-state `CheckResult` convention
  from mcp-workspace#301 — `ok=None` means "cannot verify", not "off".
- Import `CheckResult` from `mcp_workspace.github_operations._types`
  (same as `_permission_probes.py`).
- `feature: Any` — at this step there's no PyGithub import needed yet;
  keep the module's only import `CheckResult` (plus `typing.Any`).
- No other module imports this yet (wired up in Step 4).

## ALGORITHM

`_classify_vulnerability_alerts(status)`:
```
if status == 204: return ok=True, value="enabled"
if status == 404: return ok=False, value="disabled"
else:             return ok=None,  value="not accessible", error=f"HTTP {status}"
```

`_classify_security_feature(feature, display_name)`:
```
if feature is None:
    return ok=None, value="not accessible", error=f"{display_name}: requires Administration: Read"
if feature.status == "enabled":
    return ok=True, value="enabled"
else:
    return ok=False, value="disabled"
```

## DATA

Both return `CheckResult` (`TypedDict`: `ok: bool | None`, `value: str`,
`severity: Literal["error","warning"]`, optional `error: str`). Every row
in this module uses `severity="warning"` (matches mcp_coder#1180's
exit-neutral requirement — these checks never affect `overall_ok`).

## Tests to write first (`test_security_probes.py`)

```python
from mcp_workspace.github_operations._security_probes import (
    _SECURITY_KEYS,
    _classify_security_feature,
    _classify_vulnerability_alerts,
)
```

- `_classify_vulnerability_alerts`: parametrize `204 -> ok=True "enabled"`,
  `404 -> ok=False "disabled"`, and each of `401, 403, 500 -> ok=None
  "not accessible"` with `"HTTP <status>"` in `error`.
- `_classify_security_feature`:
  - `feature=None` -> `ok=None`, `"not accessible"`, `display_name` in `error`.
  - a `Mock(status="enabled")` -> `ok=True`, `"enabled"`, no `error` key.
  - a `Mock(status="disabled")` -> `ok=False`, `"disabled"`.
- `_SECURITY_KEYS` has exactly the 4 expected keys, in order:
  `dependabot_alerts`, `dependabot_security_updates`, `secret_scanning`,
  `secret_scanning_push_protection`.

## Precondition check

None — this step has no external dependency (pure functions, stdlib
`typing` only). Proceed directly to implementation.

## Commit

One commit containing both new files. Suggested message:
`test+feat(security_probes): add tri-state classifier functions`

## LLM prompt for this step

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_1.md` in this
> repo. Implement exactly what Step 1 describes: create
> `tests/github_operations/test_security_probes.py` with the classifier
> tests listed in Step 1 (write and run them first, confirming they fail
> because the module doesn't exist yet), then create
> `src/mcp_workspace/github_operations/_security_probes.py` with
> `_SECURITY_KEYS`, `_classify_vulnerability_alerts`, and
> `_classify_security_feature` per Step 1's ALGORITHM section, until the
> tests pass. Do not implement anything beyond Step 1 — no PyGithub calls,
> no `verify_github_security`, no `__init__.py` changes. Run
> `mcp__mcp-tools-py__run_pylint_check`,
> `mcp__mcp-tools-py__run_pytest_check` (with `extra_args: ["-n", "auto"]`),
> and `mcp__mcp-tools-py__run_mypy_check`; fix anything they flag. Run
> `mcp__mcp-tools-py__run_format_code`, then make exactly one commit
> covering both files.
