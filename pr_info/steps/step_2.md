# Step 2 — Probe classifier wording

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_2.md`. Use TDD: update the tests first, then the code. Run pylint, pytest (`-n auto`) and mypy until all three pass, then produce one commit.

## WHERE

- `src/mcp_workspace/github_operations/_permission_probes.py`
- `tests/github_operations/test_permission_probes.py`

## WHAT

```python
def _classify_permission_response(
    name: str, status: int, url: str, web_host: str | None
) -> CheckResult: ...

def _run_probe(
    *, call: Callable[[], object], name: str, url: str, web_host: str | None
) -> CheckResult: ...
```

Both functions lose the `admin_404` parameter.

## HOW

- The 403 branch of `_classify_permission_response` produces:
  `f"not accessible (403) — needs {name}; grant it to the token, or an org policy is blocking it{suffix}"`
- Remove the `admin_404` branch. Every 404 now gets the host-branched generic text.
- `_probe_administration` stops passing `admin_404=True`. It still calls `get_protection` itself until step 3.

## ALGORITHM

None. This step changes wording and removes a parameter.

## DATA

The 403 rows keep `ok=False, value="failed"`. Only the `error` text changes.

## Tests (write first)

- `TestClassifier403`: assert `"not accessible (403)"`, `"Issues: Read"`, `"grant it to the token"` and `"(GET {url})"` are in `err`. Assert `"blocked by org policy"` is **not** in `err`.
- Delete `TestClassifier404Admin`.
- `TestAdministrationTwoCallAttribution.test_get_protection_404_runs_classifier_with_admin_404`: rename it to `..._runs_classifier`. Assert that the generic 404 text (`"fine-grained PAT"`) is present and `"no branch protection"` is absent. Step 3 rewrites this test.
- Remove the vulture whitelist entry for `admin_404`, if one exists.
