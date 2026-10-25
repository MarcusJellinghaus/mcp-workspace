# Step 2 — `RulesOutcome`, `short_reason`, and `fetch_rules`

## LLM prompt
> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_2.md`. Step 1 is done. TDD:
> write the tests first, then the implementation. Run pylint, pytest (`-n auto`) and mypy through
> the MCP tools; all must pass. Format with `run_format_code`, then make exactly one commit.

## WHERE
- `src/mcp_workspace/github_operations/_types.py`
- `src/mcp_workspace/github_operations/verification.py` (import update only)
- `src/mcp_workspace/github_operations/_ruleset_protection.py`
- `tests/github_operations/test_ruleset_protection.py`

## WHAT
```python
# _types.py
class RulesOutcome(NamedTuple):
    """Result of the effective-rules fetch in verify_github."""
    rules: list[dict[str, Any]] | None  # set on success
    names: list[str] | None  # ruleset names; None when the lookup failed or found none
    exception: Exception | None  # None on success
    note: str | None  # pre-formatted error text; None on success

def short_reason(exc: Exception) -> str: ...  # moved unchanged from verification._short_reason

# _ruleset_protection.py
def fetch_rules(manager: BaseGitHubManager, repo: Repository, branch: str) -> RulesOutcome: ...
def _ruleset_names(requester: Any, base: str, ids: set[int]) -> list[str] | None: ...
```

## HOW
- Move `_short_reason` with `mcp__mcp-tools-py__move_symbol` (or by hand) to `_types.py` as
  `short_reason`. Update `verification.py` to import it. Nothing in `tests/` references the old name.
- `requester = manager._github_client._Github__requester` with the same
  `# type: ignore[attr-defined]  # pylint: disable=protected-access` comments as
  `_pr_feedback_sources.py:423`. The reason comment is `# no public rulesets API in PyGithub`.
- Quote the branch with `urllib.parse.quote(branch, safe="")`. `requestJsonAndCheck` does not
  encode it.
- Catch any `Exception` with the repo's existing
  `# noqa: BLE001  # pylint: disable=broad-exception-caught` comments, and log at debug level as
  `_fetch_protection` does.

## ALGORITHM
```
base = f"/repos/{repo.owner.login}/{repo.name}"
try: _, data = requester.requestJsonAndCheck("GET", f"{base}/rules/branches/{quote(branch, safe='')}", parameters={"per_page": 100})
except Exception as exc: return RulesOutcome(None, None, exc, f"rulesets not verifiable: {short_reason(exc)}")
rules = list(data or [])
names = _ruleset_names(requester, base, {r.get("ruleset_id") for r in rules}) if rules else None
return RulesOutcome(rules, names, None, None)
```

`_ruleset_names`:
- `GET {base}/rulesets` with `per_page=100`. Leave `includes_parents` at its default (true) so
  org-level rulesets resolve.
- Return the `name`s whose `id` is in `ids`, keeping the API order, or `None` if the list is empty.
- Any exception → `None`, never an error.

## DATA
- Success: `RulesOutcome([...], ["Protect main"] or None, None, None)`.
- Failure: `RulesOutcome(None, None, exc, "rulesets not verifiable: HTTP 403: ...")`.

## Tests (mocked requester: `manager._github_client._Github__requester.requestJsonAndCheck`)
- The URL quotes `release/1.x` as `release%2F1.x`; both calls pass `per_page=100`.
- Rules plus a successful lookup → names filtered to the matching `ruleset_id`s.
- `/rulesets` raises a 403 → `names is None` and `note is None`.
- Empty rules → no `/rulesets` call.
- Rules call raises 401 / 403 / 404 / 500 / `ConnectionError` → `rules is None`, `exception` is the
  raised one, `note` starts with `rulesets not verifiable: ` and contains the status (or
  `ConnectionError`).
