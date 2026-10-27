# Step 3: Raising branch-resolution core in `IssueBranchManager`

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_3.md` exactly.
> TDD: write the tests first, then the code. Run pylint, pytest (`-n auto`) and mypy;
> all must pass. One commit.

## Goal

An undecorated resolver that returns found / not_found / ambiguous and **raises** on every
error, so the branch cache (step 4) never caches an error as "no branch".
`get_branch_with_pr_fallback` becomes a thin wrapper around it — no duplicated logic.

## WHERE

- Modify `src/mcp_workspace/github_operations/issues/branch_manager.py`
- Modify `src/mcp_workspace/github_operations/issues/__init__.py` — export `BranchLookup`, `BranchLookupError`
- Tests: create `tests/github_operations/issues/test_branch_manager_resolve.py`;
  update `test_branch_manager_pr_fallback_a.py` / `_b.py`:
  - where they mock `_search_branches_by_pattern`: mock `_pattern_lookup` instead, returning a `BranchLookup`;
  - every `mock_manager.get_linked_branches = Mock(return_value=X)` and
    `mock_manager.get_linked_branches.assert_called_once_with(123)` (e.g. `_a.py:32,48,74`):
    rename to `_fetch_linked_branches` (same return values, same assertions). Mechanical rename only.
  Unaffected: `test_branch_manager_create.py` (`create_remote_branch_for_issue` keeps calling
  `get_linked_branches`), `test_branch_manager_linked.py`, `test_branch_manager_resolution.py`
  (tests of `_search_branches_by_pattern`), `test_branch_manager_integration.py` (live GitHub).

## WHAT

```python
class BranchLookup(NamedTuple):
    status: Literal["found", "not_found", "ambiguous"]
    branch: str | None = None          # set only when status == "found"

class BranchLookupError(Exception):
    """Branch resolution could not be completed (not a GitHub 'no branch' answer)."""

class IssueBranchManager:
    def resolve_branch_for_issue(
        self, issue_number: int, repo_owner: str, repo_name: str
    ) -> BranchLookup:
        """Undecorated 4-step resolution. Raises on any error."""

    def _fetch_linked_branches(self, issue_number: int) -> list[str]:
        """_query_linked_branches(self, n); None → BranchLookupError. Patchable seam for tests."""

    def _pattern_lookup(self, issue_number: int, repo: Any) -> BranchLookup:
        """Today's _search_branches_by_pattern logic, returning BranchLookup."""

    def _search_branches_by_pattern(self, issue_number: int, repo: Any) -> Optional[str]:
        return self._pattern_lookup(issue_number, repo).branch

    @log_function_call
    @_handle_github_errors(default_return=None)
    def get_branch_with_pr_fallback(self, issue_number, repo_owner, repo_name) -> Optional[str]:
        """Unchanged signature; wraps resolve_branch_for_issue."""
```

## HOW

Error mapping inside `resolve_branch_for_issue`:

| situation | today (decorated) | core |
|---|---|---|
| invalid issue number | `None` | `ValueError` |
| `_get_repository()` is `None` | `None` | `BranchLookupError` |
| `_query_linked_branches(self, n)` returns `None` | treated as `[]`, continues | `BranchLookupError` |
| `GithubException` anywhere (incl. 5xx, rate limit) | `None` / continues | propagates |
| GraphQL `data`/`repository`/`issue` is `None`, `KeyError`/`TypeError` | `None` | `BranchLookupError` |
| closed-PR probe `repo.get_branch` 404 | continue | continue (branch gone) |
| closed-PR probe other `GithubException` | continue | propagates |
| >1 linked branches / >1 open PRs / pattern ambiguous | `None` | `BranchLookup("ambiguous")` |
| nothing found | `None` | `BranchLookup("not_found")` |

- The core gets linked branches only via `self._fetch_linked_branches(n)`, which calls
  `_query_linked_branches` (module function in `linked_branches_mixin.py`) directly,
  **not** `get_linked_branches` / `get_linked_branches_or_none` (they swallow errors).
  Being a method, it is what the fallback tests mock.
- Wrapper: validate with `validate_issue_number_or_log` first (keeps today's `None` for
  invalid input), then `try: return self.resolve_branch_for_issue(...).branch`
  `except BranchLookupError as e: logger.debug(...); return None`. The decorator keeps
  today's handling of `GithubException` (rate limit/auth re-raised, others → `None`).
- Accepted behaviour change of the wrapper (release note in step 7): when the linked-branch
  query fails, it now returns `None` instead of continuing with the timeline fallback.
- Keep all existing log messages in the core.

## ALGORITHM

```
validate n (ValueError); repo = _get_repository() or raise BranchLookupError
linked = self._fetch_linked_branches(n)   # raises BranchLookupError if _query_linked_branches → None
if len(linked)==1: found; if >1: ambiguous
timeline = graphql(...); parse or raise BranchLookupError; open PRs: 1→found, >1→ambiguous
closed PRs (desc, ≤25): get_branch → found; 404 → continue; other → raise
return self._pattern_lookup(n, repo)
```

## DATA

`BranchLookup("found", "123-x")`, `BranchLookup("not_found")`, `BranchLookup("ambiguous")`.

## Tests (`test_branch_manager_resolve.py`)

- One test per row of the table above (found via linked / open PR / closed PR / pattern;
  ambiguous linked / open PRs / pattern; not_found).
- `_query_linked_branches` returning `None` (patch `linked_branches_mixin`'s function as
  imported into `branch_manager`) → `_fetch_linked_branches` raises `BranchLookupError`.
- Linked-branches GraphQL raising a rate-limit `GithubException` → propagates.
- Closed-PR probe: 404 → next PR; 500 → raises.
- Wrapper: `BranchLookupError` → `None`; invalid number → `None`; existing
  `test_branch_manager_pr_fallback_*` tests green.
