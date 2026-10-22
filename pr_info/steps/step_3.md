# Step 3 — `base_branch_trust.py`: editor lookup and body trust decision

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_3.md`.
> TDD: write the tests listed below first, see them fail, then implement.
> Run pylint, pytest (`extra_args: ["-n", "auto"]`) and mypy until all pass, then
> `run_format_code` and make one commit.

## WHERE

- New: `src/mcp_workspace/github_operations/issues/base_branch_trust.py`
- New: `tests/github_operations/issues/test_base_branch_trust.py`

Nothing calls this module yet; step 4 wires it into `IssueManager`.

## WHAT

```python
def fetch_body_editor(
    manager: BaseGitHubManager, repo: Repository, issue_number: int
) -> Optional[str]:
    """Return the login of the issue body's last editor.

    Returns None when the body was never edited or the lookup failed.
    Bot logins get the "[bot]" suffix. Never raises.
    """

def is_body_trusted(
    manager: BaseGitHubManager,
    repo: Repository,
    issue_number: int,
    author_login: Optional[str],
    author_association: Optional[str],
    allowlist: Callable[[], frozenset[str]],
) -> bool:
    """Decide whether an issue body may choose the base branch. Never raises."""
```

## HOW

- GraphQL via `manager._github_client._Github__requester.graphql_query(query=..., variables=...)`,
  with the same `# type: ignore[attr-defined]` and pylint disables as
  `linked_branches_mixin.py` ~132.
- Query:
  `query($owner:String!,$repo:String!,$number:Int!){repository(owner:$owner,name:$repo){issue(number:$number){editor{__typename login}}}}`.
  Variables come from `repo.owner.login`, `repo.name` and `issue_number`.
- The token user comes from `_cached_login(manager.github_token,
  manager._repo_identifier.api_base_url, manager._github_client)`, imported from
  `..base_manager`, as in `server.py` ~205.
- Catch every exception (`# pylint: disable=broad-exception-caught`) in both lookups and
  log it at DEBUG with `exc_info=True`. A failed lookup means the editor is untrusted.
- Reuse `is_trusted_author` from `..trust`; don't reimplement the rule.

## ALGORITHM

```
is_body_trusted:
    if is_trusted_author(author_login, author_association, frozenset()): return True  # role only, no allowlist read
    if is_trusted_author(author_login, author_association, allowlist()): return True
    editor = fetch_body_editor(manager, repo, issue_number)
    if editor is None: return False
    if editor.lower() in allowlist(): return True
    try: return editor.lower() == _cached_login(...).lower()
    except Exception: log debug; return False
```

`fetch_body_editor`:
- Take `result["data"]["repository"]["issue"]["editor"]`.
- Missing or None at any level → None (a GraphQL `{"data": None, "errors": [...]}`
  response included).
- Otherwise return `login + "[bot]"` if `__typename == "Bot"`, else `login`.

## DATA

- `fetch_body_editor` → `Optional[str]` (login).
- `is_body_trusted` → `bool`.
- `allowlist` is a zero-argument callable. Step 4 passes
  `functools.cache(config.get_trusted_commenters)`, so the file is read at most once per
  manager call and only when needed.

## Tests (write first)

`manager` is a `MagicMock`. Patch `graphql_query`, and patch `_cached_login` where
`base_branch_trust` looks it up.

`fetch_body_editor`:
- a `User` editor → its login;
- a `Bot` editor → `"name[bot]"`;
- a null editor → None;
- an `{"data": None, "errors": [...]}` response → None;
- `graphql_query` raises `GithubException` → None, no exception.

`is_body_trusted`:
- an `OWNER` / `MEMBER` / `COLLABORATOR` author → True, without calling `allowlist` or
  `graphql_query`;
- an allowlisted author with association `NONE` → True, no GraphQL request;
- an untrusted author whose editor is the token user → True;
- an untrusted author with an allowlisted editor → True, and `_cached_login` is not
  needed;
- an allowlisted Bot editor (`dependabot[bot]`) → True;
- an untrusted author with an untrusted editor → False;
- an untrusted author with no editor → False;
- the editor lookup fails → False;
- `_cached_login` raises → False;
- ghost author (`author_login=None`, `author_association=None`), no editor → False, no
  crash.
