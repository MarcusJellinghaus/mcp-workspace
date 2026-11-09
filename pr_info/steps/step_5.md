# Step 5 — `issues/status.py`: `set_issue_status`

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement **Step 5** exactly as described
> in `pr_info/steps/step_5.md`. Steps 1, 3 and 4 (`get_cached_labels`,
> `get_issue_for_status`, `set_issue_labels_in_cache`) are already done. Write
> the tests first, then the code. Run pylint, pytest (`-n auto`), mypy and
> lint-imports via the MCP tools until all pass, format the code, and make
> exactly one commit.

## Precondition

`get_cached_labels`, `LabelsMixin.get_issue_for_status` and
`set_issue_labels_in_cache` all exist. If any is missing, write one line to
`pr_info/.blocked.txt` and stop.

## WHERE

- `src/mcp_workspace/github_operations/issues/status.py` (new)
- `tests/github_operations/issues/test_status.py` (new)

## WHAT

```python
STATUS_LABEL_PREFIX = "status-"

def is_status_label(name: str) -> bool:
    return name.casefold().startswith(STATUS_LABEL_PREFIX)

def set_issue_status(
    manager: IssueManager,
    number: int,
    status: str,
    from_status: str | None = None,
    refresh_labels: bool = False,
) -> str:
    """Move an issue to `status`; return the user-facing result text."""
```

## HOW

- Imports: `..caching.labels.get_cached_labels`, `.cache.set_issue_labels_in_cache`,
  and `IssueManager` under `TYPE_CHECKING`.
- Errors from `get_cached_labels` (rate limit with no entry, 5xx, …) and from
  `get_issue_for_status` (404, PR `ValueError`, …) propagate. The server
  renders them through `_tool_error`.
- Use `manager.set_labels(number, *new_labels)`, **not** `transition_issue_label`.
- Compare case-insensitively everywhere. Write the repo's own spelling, taken
  from the label cache.

## ALGORITHM

```
labels, footer = get_cached_labels(manager, refresh=refresh_labels)
known = {l["name"].casefold(): l for l in labels if is_status_label(l["name"])}
for value in [status] + ([from_status] if from_status is not None else []):
    if value.casefold() not in known: return _invalid(value, known.values(), footer)
target = known[status.casefold()]["name"]
issue = manager.get_issue_for_status(number); current = [l for l in issue["labels"] if is_status_label(l)]
if from_status is not None and [c.casefold() for c in current] != [from_status.casefold()]: return guard message
if [c.casefold() for c in current] == [target.casefold()]: return no-op message
result = manager.set_labels(number, *([l for l in issue["labels"] if not is_status_label(l)] + [target]))
if result["number"] == 0: return unconfirmed message   # coordinator cache untouched
set_issue_labels_in_cache(manager.repo_identifier, number, result["labels"]); return changed message
```

## DATA

Exact result texts (`<old>` = the current status labels joined with ", ", or `<none>`).
Append `\nNote: issue #N is closed.` when `issue["state"] == "closed"`, for
every outcome after the issue read.

- invalid: `Label "<value>" not found. Available status labels:` then one line
  per cached status label, `<name>  <description>` (rstripped), or `(none)`,
  then `<footer>`
- guard failed: `Status of issue #N not changed: current status is <old>, not <from_status>.`
- no-op: `Issue #N already has status <target>; nothing changed.`
- changed: `Issue #N status: <old> → <target>` then `Labels: <result labels joined by ", " or (none)>`
- unconfirmed: `Error: write to issue #N failed or unconfirmed — re-check with github_issue_view`

## Tests (write first)

Use a `MagicMock` manager with `repo_identifier = RepoIdentifier("owner", "repo")`
and patch `mcp_workspace.github_operations.issues.status.get_cached_labels` and
`...status.set_issue_labels_in_cache`.

- `status="2"`, or a non-`status-` label such as `"bug"` → invalid text lists
  only the `status-*` labels with descriptions and ends with the footer. No
  issue read and no `set_labels` call.
- `from_status` unknown → invalid text, no write
- `"STATUS-03:Foo"` matches the cached `"status-03:foo"`; `set_labels`
  receives the repo spelling
- a change removes every other `status-*` label and keeps non-status labels
- the result shows old → new and the labels returned by `set_labels` (not the requested set)
- guard mismatch → no write, reports the actual status; no status → `<none>`;
  several status labels → guard fails and lists them all
- guard match → write happens
- already in target with no other status label → no-op, no write
- in target plus another status label → write (not a no-op)
- closed issue → updated, with the closed note
- `set_labels` returns `number == 0` → unconfirmed text, and
  `set_issue_labels_in_cache` is not called
- success → `set_issue_labels_in_cache(repo_identifier, N, result["labels"])` called once
- the `get_issue_for_status` exception (404 / PR `ValueError`) propagates
