# Step 2 — Switch to `latestOpinionatedReviews`; add `submitted_at` and `ChangesRequestedData`

See `pr_info/steps/summary.md` for full architecture and context.

## Precondition — check before making any change

Issue #324's Decisions table requires a live test-repo check of `latestOpinionatedReviews`'s behavior (request changes → approve; request changes → comment; dismissal) before this query is reshaped, because a negative result would require a different approach (client-side reduction) that changes the query and every test built around it.

Call `mcp__mcp-workspace__github_issue_view(number=324, include_comments=True)` and read the comments. If no comment reports a result of that live test-repo check (confirming or refuting `latestOpinionatedReviews` drops a superseded `CHANGES_REQUESTED` once the same reviewer approves/comments, and reflects dismissal), write one line to `pr_info/.blocked.txt`:

```
Blocked: live-test-repo verification for latestOpinionatedReviews (issue #324) not yet reported.
```

and stop. Do not edit any other file in this step.

If a result is reported and confirms the documented behavior, proceed with the rest of this step unchanged. (If it reports a contradiction, this step's plan is invalid — write the same `.blocked.txt` line instead of improvising a fallback.)

## WHERE

- `src/mcp_workspace/github_operations/pr_types.py` — add `ChangesRequestedData`; retype `PRFeedback.changes_requested`.
- `src/mcp_workspace/github_operations/_pr_feedback_sources.py` — query field rename, new parsing helpers.
- `src/mcp_workspace/github_operations/pr_feedback_mixin.py` — docstring wording ("standing" CHANGES_REQUESTED), ~line 114.
- `tests/github_operations/test_pr_feedback_mixin.py` — rename the `reviews` key to `latestOpinionatedReviews` in `_EMPTY_REVIEW_DATA` and every mock GraphQL body (~14 occurrences), including the two GraphQL error `"path"` arrays that currently read `["repository", "pullRequest", "reviews"]` and `["repository", "pullRequest", "reviews", "nodes", 0]`; add new tests listed below.

## WHAT

```python
# pr_types.py
class ChangesRequestedData(TypedDict):
    """TypedDict for one standing CHANGES_REQUESTED review."""

    author: str
    body: str
    submitted_at: Optional[str]
```

```python
# _pr_feedback_sources.py
def _parse_submitted_at(raw: Optional[str]) -> Optional[str]:
    """Normalize a GraphQL submittedAt value to isoformat, or None on absence/bad input."""

def _parse_changes_requested(pr_data: dict[str, Any]) -> list["ChangesRequestedData"]:
    """Build standing CHANGES_REQUESTED entries from latestOpinionatedReviews nodes."""
```

## HOW

- Query change inside `fetch_review_data` — only the reviews field, `reviewThreads` untouched in this step:
  ```graphql
  latestOpinionatedReviews(first: 50) {
    nodes { state author { login } body submittedAt }
  }
  ```
  (First-page size and pagination arrive in step 4 — kept at `50` here to minimize this step's diff.)
- `fetch_review_data`'s inline `changes_requested` loop is replaced by `changes_requested = _parse_changes_requested(pr_data)`.
- `fetch_review_data`'s return type annotation changes from `list[dict[str, Any]]` to `list[ChangesRequestedData]` for the 3rd tuple element (import `ChangesRequestedData` from `.pr_types`, matching the existing `ConversationCommentData` import pattern under `TYPE_CHECKING`).
- `PRFeedback.changes_requested` in `pr_types.py`: `list[dict[str, Any]]` → `list[ChangesRequestedData]`.
- `pr_feedback_mixin.py`'s `get_pr_feedback` docstring: "CHANGES_REQUESTED reviews" → "standing CHANGES_REQUESTED reviews". `fetch_review_data`'s own docstring and `PRFeedback`'s docstring get the same wording.
- `datetime` import added to `_pr_feedback_sources.py` for `_parse_submitted_at`.

## ALGORITHM

```
_parse_submitted_at(raw):
    if raw is None: return None
    try: return datetime.fromisoformat(raw).isoformat()
    except ValueError: log.debug("unparseable submittedAt: %r", raw); return None

_parse_changes_requested(pr_data):
    result = []
    for node in (pr_data.get("latestOpinionatedReviews") or {}).get("nodes") or []:
        if node is None or node.get("state") != "CHANGES_REQUESTED":
            continue
        result.append({
            "author": (node.get("author") or {}).get("login") or "",
            "body": node.get("body") or "",
            "submitted_at": _parse_submitted_at(node.get("submittedAt")),
        })
    return result
```

## DATA

`ChangesRequestedData` as above. `fetch_review_data` still returns a 4-tuple; only the 3rd element's item shape gains `submitted_at`. No change to `unresolved_threads`/`resolved_count`/`error`.

## Tests (write first)

In `tests/github_operations/test_pr_feedback_mixin.py`:

- Rename every mock `"reviews"` key (in `_EMPTY_REVIEW_DATA` and all per-test GraphQL bodies) to `"latestOpinionatedReviews"`, including the two error-path tests whose `"path"` arrays reference `"reviews"`.
- `test_happy_path`: assert `result["changes_requested"][0]["submitted_at"] == "2025-01-01T00:00:00+00:00"` (from the existing mock's `"2025-01-01T00:00:00Z"`).
- New: two `CHANGES_REQUESTED` nodes from different reviewers in one mocked `latestOpinionatedReviews` response → both appear as separate entries (documents that reduction is GitHub's job, not new code here).
- New, parametrized: `submittedAt` is `None` → `submitted_at is None`; `submittedAt` is `"not-a-date"` → `submitted_at is None` and a DEBUG log line is emitted (`caplog.at_level(logging.DEBUG, ...)`).
- New: two `CHANGES_REQUESTED` nodes with `author: None` → both entries kept, each with `author == ""` (no accidental de-duplication on empty author).

In `pr_types.py`/mypy: no dedicated test needed — `run_mypy_check` enforces the TypedDict shape.

## Commit

One commit: type + query/parsing rewrite + docstrings + tests above.

## LLM Prompt

> Implement `pr_info/steps/step_2.md` for issue #324 (architecture in `pr_info/steps/summary.md`). First run the precondition check exactly as written in this step file — if unmet, write the one blocked line and stop, making no other change. If met, follow TDD: update/add the tests listed in this step first (including the `reviews` → `latestOpinionatedReviews` renames), confirm they fail, then add `ChangesRequestedData`, the query field rename, and the parsing helpers until green. Do not touch `reviewThreads` or add pagination — that is step 4. Run `mcp__mcp-tools-py__run_ruff_check`, `run_pylint_check`, `run_pytest_check` (`extra_args: ["-n", "auto"]`), and `run_mypy_check` until clean, then make exactly one commit.
