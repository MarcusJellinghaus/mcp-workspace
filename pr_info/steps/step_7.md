# Step 7 — README and `tests/LLM_Test.md`

## LLM prompt

> Read `pr_info/steps/summary.md` and this file, `pr_info/steps/step_7.md`.
> Steps 1–6 must be committed (`body_file` on all four tools, approximate count, `show_allowlisted`); if any is
> missing, write one line to `pr_info/.blocked.txt` and stop.
> Docs only — no code changes. Run pytest (`-n auto`) to confirm `tests/test_tool_descriptions.py` and any
> README checks still pass. Run format_code, then make one commit.

## WHERE
- `README.md` — tool table (≈ lines 358–367)
- `tests/LLM_Test.md`

## WHAT / HOW

README tool table — minimal edits to the description column:
- `github_issue_create`, `github_issue_edit`, `github_issue_comment`, `github_pr_create`: mention the body can
  come from a project file (`body_file`).
- `github_subissue_add` / `github_subissue_remove`: count is approximate; `github_subissue_list` for the exact set.
- `check_file_size`: `show_allowlisted=True` lists allowlisted files with sizes.

`tests/LLM_Test.md`:
- Line ≈209: expectation becomes `... — <url> (~1 sub-issues, may lag)`.
- After line ≈100: `check_file_size(show_allowlisted=True)` — expect a first line
  `Allowlisted files (N), limit M:` followed by one line per entry, and no pass/fail line.
- Section 4 (issue writes): `save_file(".scratch/llm_body.md", "Line 1\nLine `2` ✓")`, then
  `github_issue_create(title="LLM test - safe to close", body_file=".scratch/llm_body.md")` — expect
  `Created issue #N`; `github_issue_view` shows the file text. Then
  `github_issue_create(title="x", body="y", body_file=".scratch/llm_body.md")` — expect a both-given error.
  Delete `.scratch/` afterwards.

## ALGORITHM / DATA
N/A.
