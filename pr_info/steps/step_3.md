# Step 3 — `check_branch_status` gate: PR feedback and ❌ issue note

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_3.md` exactly.
> Steps 1 and 2 are done. Write the tests first, then the code. Run pylint, pytest (`-n auto`),
> mypy and tach (`mcp__mcp-tools-py__run_tach_check`) until they all pass, then make exactly one commit.
>
> Precondition: `is_trusted_author` exists and `ReviewThreadData` / `CommentData` carry
> `author_association`. If they don't, write one line to `pr_info/.blocked.txt` and stop.

## WHERE

- `src/mcp_workspace/github_operations/formatters.py` — add `format_withheld_line`
- `src/mcp_workspace/checks/pr_feedback.py` — `format_pr_feedback`, `collect_pr_feedback`
- `src/mcp_workspace/checks/branch_status.py` — `collect_branch_status`
- `tach.toml` — add `{ path = "mcp_workspace.config" }` to the `depends_on` of the
  `mcp_workspace.checks` module (CI runs `tach check`; `.importlinter` already allows it)
- `tests/github_operations/test_formatters.py`
- `tests/checks/test_branch_status_pr_feedback.py`
- `tests/checks/test_branch_status.py`

## WHAT

```python
# formatters.py
def format_withheld_line(counts: list[tuple[str, int]]) -> Optional[str]: ...

# pr_feedback.py
def format_pr_feedback(feedback: PRFeedback, trusted: frozenset[str]) -> str: ...
def collect_pr_feedback(
    pr_manager: PullRequestManager, pr_number: int, trusted: frozenset[str]
) -> Tuple[Optional[str], bool, bool]: ...
```

`trusted` is required, with no default. Update every existing call site, in both src and tests.

## HOW

- `pr_feedback.py` imports `is_trusted_author` from `mcp_workspace.github_operations.trust` and
  `format_withheld_line` from `mcp_workspace.github_operations.formatters`.
- `branch_status.py`: add `from mcp_workspace import config` at module level. In `collect_branch_status`, call
  `trusted = config.get_trusted_commenters()` once, before the GitHub block. Use it for the ❌ filter
  and pass it to `collect_pr_feedback(pr_manager, pr_number, trusted)`. The call-time attribute
  lookup is what the conftest autouse patch from step 1 relies on.
- Import `is_trusted_author` in `branch_status.py` for the ❌ filter.
- `find_latest_marked_comment` stays unchanged.

## ALGORITHM

```
format_withheld_line(counts):   # counts = [("thread", 2), ("review", 1), ...] singular kind names
    parts = [f"{n} {kind if n == 1 else kind + 's'}" for kind, n in counts if n > 0]
    return None if not parts else f"Withheld from untrusted authors: {', '.join(parts)} — review on GitHub"

format_pr_feedback(feedback, trusted):
    ok = lambda item: is_trusted_author(item["author"], item["author_association"], trusted)
    split unresolved / changes_requested / comments into kept (ok) and withheld counts
    blocking + clean check use the FULL lists (unchanged semantics)
    existing loops render only the kept lists -> cap / body_cut / _FULL_TEXT_HINT ignore withheld
    lines = ["PR Reviews:", withheld_line (if any), *rendered, unavailable..., resolved..., hint...]

collect_branch_status ❌ note:
    trusted_comments = [c for c in comments if is_trusted_author(c["user"], c["author_association"], trusted)]
    last_automated_note = find_latest_marked_comment(trusted_comments)
```

Count kinds for `check_branch_status`: `thread` (unresolved threads), `review` (changes_requested),
`comment` (conversation comments). Alerts are never withheld.

## DATA

- Output for an untrusted item: no per-item line, so no body, diff hunk, path, login,
  `comment_id` or `thread_id`. Only the one count line, e.g.
  `Withheld from untrusted authors: 2 threads, 1 review, 5 comments — review on GitHub`.
- `collect_pr_feedback`: `blocks_merge` and `undeterminable` are computed exactly as before.

## Tests (write first)

`test_formatters.py` — `format_withheld_line`:
- all zeros → `None`
- `[("thread", 2), ("review", 1), ("comment", 0)]` → `"Withheld from untrusted authors: 2 threads, 1 review — review on GitHub"`

`test_branch_status_pr_feedback.py` — `format_pr_feedback`:
- `OWNER`, `COLLABORATOR`, and an allowlisted bot (`author="dependabot[bot]"`,
  `author_association="NONE"`, `trusted=frozenset({"dependabot[bot]"})`) → body shown
- an untrusted thread with `comment_id`/`thread_id`/path set → none of the body, login, path or ids appears
  in the output; the count line is present
- a mixed list → trusted items rendered, and the count line has the right number for each kind
- 25 untrusted comments + 1 trusted → the cap does not fire, and `_FULL_TEXT_HINT` is absent
- an untrusted 50-line body → `_FULL_TEXT_HINT` is absent
- `collect_pr_feedback`: an untrusted unresolved thread or untrusted changes-requested review →
  `blocks_merge is True`
- Pass `trusted=frozenset()` in every existing call.

`test_branch_status.py` — ❌ note through `collect_branch_status` (mocked `IssueManager`):
- an untrusted (`CONTRIBUTOR`) ❌ comment → `last_automated_note is None`
- an `OWNER` ❌ comment followed by 3 untrusted comments → the owner's note is still found
- an `OWNER` ❌ comment → shown (the existing test, with `"OWNER"` from the fixture default)
