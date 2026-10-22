# Step 6 — `[untrusted @login]` prefix in list, search and sub-issue tools; README trust section

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_6.md`.
> TDD: write the tests listed below first, see them fail, then implement.
> Run pylint, pytest (`extra_args: ["-n", "auto"]`) and mypy until all pass, then
> `run_format_code` and make one commit.
>
> Precondition: `_allowlist_for` from step 5 exists in `server.py`. If it doesn't, write
> one line to `pr_info/.blocked.txt` and stop.

## WHERE

- `src/mcp_workspace/github_operations/formatters.py`
- `src/mcp_workspace/server.py` (`github_issue_list`, `github_search`, `github_subissue_list`)
- `README.md` (~94–109, `trusted_commenters` / "Commenter trust")
- Tests:
  - `tests/github_operations/test_formatters.py` (existing list/search calls gain
    `trusted=frozenset()`, and their fixtures carry an association)
  - `tests/github_operations/test_github_search_tool.py` (existing `MagicMock` search
    items gain `author_association="OWNER"`)
  - `tests/github_operations/test_github_write_tools_subissues.py` (existing `MagicMock`
    sub-issue children gain `author_association="OWNER"`)
  - Without that, a bare `MagicMock` attribute normalises to `None` (untrusted) and every
    existing row assertion gains `[untrusted @…]` and fails.
  - `tests/github_operations/test_github_read_tools_issues.py`

## WHAT

```python
def untrusted_prefix(
    login: Optional[str], association: Optional[str], trusted: frozenset[str]
) -> str:
    """Return "[untrusted @login] " for an untrusted author, else ""."""

def format_issue_list(issues, max_results=30, repo_full_name=None, *, trusted: frozenset[str]) -> str
def format_search_results(items, max_results=30, total_count=None, *, trusted: frozenset[str]) -> str
```

## HOW

- `untrusted_prefix` reuses `is_trusted_author`; a ghost renders as `@ghost`.
- `format_issue_list` row:
  `f"#{n} [{state}] {untrusted_prefix(issue['user'], issue.get('author_association'), trusted)}{title}{label_part}"`.
- `format_search_results` row:
  `f"#{n} [{kind}] [{state}] {untrusted_prefix(item.get('user'), item.get('author_association'), trusted)}{title}{label_part}"`.
- `github_search` item dict adds
  `"user": item.user.login if item.user else None` and
  `"author_association": normalize_author_association(item.author_association)`.
- `github_subissue_list`:
  - compute `trusted = _allowlist_for(...)` over the children's normalised associations;
  - render `f"#{c.number}  {c.state}  {untrusted_prefix(login, assoc, trusted)}{c.title}"`,
    where `login = c.user.login if c.user else None`;
  - update the Returns line of the docstring.
- `github_issue_list` and `github_search` compute `trusted` with `_allowlist_for` over
  their items before calling the formatter.
- No fence is needed: titles are single-line.
- README:
  - `trusted_commenters` also covers body editors (the Base Branch gate);
  - issue text from untrusted authors in `github_issue_view` is fenced and labelled, not
    withheld;
  - list, search and sub-issue rows get `[untrusted @login]`;
  - `### Base Branch` is ignored unless the author is trusted or the last body editor is
    the token user or allowlisted;
  - PR feedback stays withheld.

## DATA

- Row strings gain an optional `"[untrusted @login] "` before the title. Trusted rows are
  unchanged.
- The search item dict gains `user: Optional[str]` and `author_association: Optional[str]`.

## Tests (write first)

`untrusted_prefix`:
- an OWNER author → `""`;
- a NONE author → `"[untrusted @abc] "`;
- a ghost author → `"[untrusted @ghost] "`;
- an allowlisted login → `""`.

Formatters:
- `format_issue_list`: an untrusted row reads `#412 [open] [untrusted @abc] Fix login`,
  and a trusted row has no prefix;
- an issue dict without the `author_association` key (stale cache) → treated as
  untrusted, no crash;
- `format_search_results`: the same two checks.

Tools:
- `github_search` maps `item.user.login` and `item.author_association` into the item
  dict (`user=None` → None), and its output shows the prefix for an untrusted item;
- `github_subissue_list`: an untrusted child gets the prefix, a trusted child doesn't,
  and a ghost child gets `@ghost`;
- `github_issue_list`: an untrusted issue gets the prefix end to end.
