# Step 4 — `github_pr_view` gate: title/body, reviews, comments, inline comments

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_4.md` exactly.
> Steps 1–3 are done (`format_withheld_line` and `is_trusted_author` exist). Write the tests first,
> then the code. Run pylint, pytest (`-n auto`), mypy and tach (`mcp__mcp-tools-py__run_tach_check`)
> until they all pass, then make exactly one commit.
>
> Precondition: `format_withheld_line` exists in `formatters.py`. If it doesn't, write one line to
> `pr_info/.blocked.txt` and stop.

## WHERE

- `src/mcp_workspace/github_operations/formatters.py` — `format_pr_view`
- `src/mcp_workspace/server.py` — `github_pr_view` (~line 1069)
- `tach.toml` — add `{ path = "mcp_workspace.config" }` to the `depends_on` of the
  `mcp_workspace.server` module (CI runs `tach check`)
- `tests/github_operations/test_formatters.py` (`TestFormatPrView`)
- `tests/github_operations/_github_read_tools_helpers.py` (`mock_pull`)
- `tests/github_operations/test_github_read_tools_pr_search.py`

## WHAT

```python
# formatters.py
def format_pr_view(
    pr: dict[str, Any],
    reviews: Optional[list[ReviewData]] = None,
    conversation_comments: Optional[list[ConversationCommentData]] = None,
    inline_comments: Optional[list[InlineCommentData]] = None,
    max_lines: int = 200,
    *,
    trusted: frozenset[str],
) -> str: ...
```

`trusted` is keyword-only and required. Update all existing calls.

## HOW

- `server.py` `github_pr_view`:
  - Add a lazy `from mcp_workspace import config` and `normalize_author_association`
    (already imported in step 2).
  - Call `trusted = config.get_trusted_commenters()` once per call. Keep this lookup through
    `mcp_workspace.config`; do not import `get_trusted_commenters` from the
    `mcp_workspace.github_operations` re-export. Otherwise the conftest autouse patch on
    `mcp_workspace.config.get_trusted_commenters` no longer applies.
  - `pr_dict` gains:
    - `"user": pr.user.login if pr.user else None`
    - `"author_association": normalize_author_association(pr.author_association)`
  - Make the item logins ghost-safe:
    - `ReviewData.user` / `InlineCommentData.user`: `x.user.login if x.user else None`
    - `ConversationCommentData.author`: `c.user.login if c.user else ""`
  - Pass `trusted=trusted` to `format_pr_view`.
- `format_pr_view` imports `is_trusted_author` from `mcp_workspace.github_operations.trust`.
- `mock_pull` in `_github_read_tools_helpers.py` sets `pr.user.login = "alice"` and
  `pr.author_association = "OWNER"`. The review and comment mocks in the existing `github_pr_view` tests
  set `author_association = "OWNER"`.

## ALGORITHM

```
author_ok = is_trusted_author(pr.get("user"), pr.get("author_association"), trusted)
title_line = f"# PR #{n}: {title}" if author_ok else
             f"# PR #{n} by @{pr.get('user') or 'unknown'} — untrusted author: title and body withheld, review on GitHub"
split reviews (user), conversation_comments (author), inline_comments (user) into kept + withheld counts
header = State line; if withheld_line: header += "\n" + withheld_line   # survives max_lines
parts = [title_line, header] + ([body or "(no description)"] if author_ok else []) + existing sections over kept lists
```

Count kinds for `github_pr_view`: `review`, `comment`, `inline comment` (pluralised by
`format_withheld_line`). Each inline comment is judged on its own, so an untrusted reply inside a
trusted thread is withheld while the trusted opener is shown. Section headers such as
`## Comments (N)` count only the kept items, and a section with no kept items is left out.

## DATA

- An untrusted PR author → `# PR #7 by @mallory — untrusted author: title and body withheld, review on GitHub`.
  State, head → base, Draft and Merged are still shown. The head branch name is unchanged.
- `## Reviews`, `## Comments (N)` and `## Inline Review Comments (N)` contain trusted items only.

## Tests (write first)

`test_formatters.py` (`TestFormatPrView`, `trusted=frozenset()`):
- untrusted PR author (`author_association="CONTRIBUTOR"`) → the title and body text are absent, the
  withheld-title line is present, and the head branch is shown
- an allowlisted PR author (`"user": "alice"`, `"author_association": "CONTRIBUTOR"`,
  `trusted=frozenset({"alice"})`) → title/body shown
- an untrusted review → its body and login are absent; the count line says `1 review`
- inline: a trusted opener and an untrusted reply → the opener is shown, the reply body is absent, and
  `1 inline comment` is counted
- the count line sits directly after the State line (single `\n`), so it survives `max_lines=4`
  (title, blank, State, count line)
- trusted-only input → output identical to before, apart from the explicit `trusted` argument
- Update the existing `TestFormatPrView` `pr` dict fixtures, and any other test caller of
  `format_pr_view`, to include `"author_association": "OWNER"` and a `user`. Otherwise the PR author
  is untrusted and the existing title/body assertions fail. `pr["user"]` is the login string, as
  built in `server.py` (`pr.user.login`), e.g. `"user": "owner"`, not a nested dict.

`test_github_read_tools_pr_search.py`:
- ghost users (`pr.user = None`, review/comment/inline `user = None`) → no crash, and they are treated
  as untrusted (withheld or counted)
- `include_comments=True` with an `OWNER` review/comment → shown as before
