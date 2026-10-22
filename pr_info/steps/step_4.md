# Step 4 — Base Branch gate in `IssueManager`

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_4.md`.
> TDD: write the tests listed below first, see them fail, then implement.
> Run pylint, pytest (`extra_args: ["-n", "auto"]`) and mypy until all pass, then
> `run_format_code` and make one commit.
>
> Precondition: `issues/base_branch_trust.py` from step 3 exists and exports
> `is_body_trusted`. If it doesn't, write one line to `pr_info/.blocked.txt` and stop.

## WHERE

- `src/mcp_workspace/github_operations/issues/manager.py`
- Tests:
  - `tests/github_operations/issues/test_manager_base_branch.py`
  - `tests/checks/test_branch_status_base_branch.py`
  - `tests/test_server_get_base_branch.py`

## WHAT

`_parse_base_branch_fields` takes the issue and the trust inputs instead of just the body:

```python
def _parse_base_branch_fields(
    manager: BaseGitHubManager,
    repo: Repository,
    github_issue: Issue,
    allowlist: Callable[[], frozenset[str]],
) -> tuple[Optional[str], Optional[str]]:
    """Return (base_branch, base_branch_error), or (None, None) for an untrusted body."""
```

## HOW

- `from mcp_workspace import config`, and call it as `config.get_trusted_commenters`, so
  the autouse test patch applies (the same pattern as `branch_status.py` ~504).
- `get_issue`: `allowlist = functools.cache(config.get_trusted_commenters)`, then
  `_parse_base_branch_fields(self, repo, github_issue, allowlist)`.
- `_list_issues_no_error_handling`: create the cached `allowlist` once, before the loop,
  and pass it for every issue.
- `is_body_trusted` never raises. That means editor and token-login failures can't reach
  `@_handle_github_errors` on `get_issue`, and they can't abort `list_issues`.
- Keep `_warned_malformed_base_branch` and the log-once WARNING exactly as today, but
  only for trusted bodies.
- Update the `base_branch` / `base_branch_error` docstrings of `get_issue` and
  `list_issues`: both are None when the body is untrusted.

## ALGORITHM

```
body = github_issue.body or ""
try: value, error = parse_base_branch(body), None
except MalformedBaseBranchError as exc: value, error = None, exc
if value is None and error is None: return None, None          # no section → no editor request
login = github_issue.user.login if github_issue.user else None
assoc = normalize_author_association(github_issue.author_association)
if not is_body_trusted(manager, repo, github_issue.number, login, assoc, allowlist):
    logger.info("Issue #%d: ignoring Base Branch section from untrusted author @%s", number, login or "ghost")
    return None, None
if error is None: return value, None
# trusted + malformed: existing message + log-once WARNING, return (None, message)
```

## DATA

`IssueData["base_branch"]` / `["base_branch_error"]`:

| Body | Result |
|---|---|
| Trusted | today's values (plus the ref-name check from step 1) |
| Untrusted | `None` / `None` |
| No section | `None` / `None`, with no extra request |

## Tests (write first)

Manager tests use `mock_issue_manager`. Mock issues come from `make_mock_issue`, with
`author_association` overridden where needed. Patch `fetch_body_editor` and
`_cached_login` in `base_branch_trust`.

`get_issue` and `list_issues`:
- untrusted author (`NONE`) with a valid section and no editor → both fields None;
- the same with a malformed section → both None, and no "malformed base branch"
  WARNING (caplog);
- an INFO log naming the issue number and author login;
- untrusted author with a token-user editor → section used;
- untrusted author with an allowlisted editor (monkeypatch
  `mcp_workspace.config.get_trusted_commenters`) → used;
- untrusted author with an untrusted editor → ignored;
- trusted author (`OWNER`) → `fetch_body_editor` is not called;
- untrusted author without a Base Branch section → `fetch_body_editor` is not called;
- trusted author with `main branch` → `base_branch_error` set (ref message).

Failure handling:
- `list_issues` where the editor lookup raises inside `graphql_query` → the section is
  ignored and the list is still returned;
- `get_issue` where the editor lookup fails → the issue is returned (number ≠ 0) and the
  section is ignored;
- `get_issue` where `_cached_login` raises → editor untrusted, section ignored.

Allowlist laziness:
- `list_issues` over three untrusted issues reads `get_trusted_commenters` at most once;
- over trusted issues it never reads it.

End to end:
- `check_branch_status`: a real `IssueManager` over a mocked repository with an
  untrusted malformed section → no MALFORMED line and no Review Gate block from the base
  branch.
- `get_base_branch`: the same setup → not `Error: issue #N: …`.

The existing base-branch, cache and branch-status tests still pass, because
`make_mock_issue` defaults to `OWNER` since step 2.
