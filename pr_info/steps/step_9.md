# Step 9 — Docs: README, `LIBRARY_USE.md`, `LLM_Test.md`

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_9.md`: update the user docs
> for `body_file` on `github_issue_view` and for the line-ending behaviour of the file tools.
> No code changes. Run `check_file_size` and pytest (`-n auto`), all green, then make one commit.

## WHERE

- `README.md` — 733/750 lines. **Edit existing lines only, add none.**
- `docs/LIBRARY_USE.md`
- `tests/LLM_Test.md`

## WHAT

- **README `:49`, `:50`, `:53`** (tool list): add "keeps the file's line endings" to `save_file`,
  `append_file` and `edit_file`. The tool list mirrors the docstrings.
- **README `:374`, `:375`, `:378`** (table): add a short note to each description, e.g.
  "…; keeps existing line endings".
- **README `:384`:** add "; `body_file` saves the raw body for read-modify-write" to the
  description of `github_issue_view`.
- **README `:134`:** append "With `body_file`, the raw body goes to the file unfenced; only the
  title stays fenced in the reply."
- **`docs/LIBRARY_USE.md`**, `read_only` bullet (`:35`) or the `workspace.github` row (`:46`): add
  "Exception: `github_issue_view` with `body_file` writes one project file (`save_file` path
  rules)."
- **`tests/LLM_Test.md` Test 4.1b:** after step 3 (view), insert steps for the round trip and
  renumber:
  1. `github_issue_view(number=<N>, body_file=".scratch/llm_view.md")` — expect a pointer line
     `(body saved to .scratch/llm_view.md, 2 lines, …)` and no body text.
  2. `edit_file(".scratch/llm_view.md", "Line 1", "Line one")` — expect a one-line diff.
  3. `github_issue_edit(number=<N>, body_file=".scratch/llm_view.md")` — expect `Applied: body`.
  4. `github_issue_view(number=<N>)` — expect `Line one` and the rest unchanged.

## Checks

- `check_file_size`: README stays ≤ 750 lines and no new violations appear.
- Run pytest anyway (`test_tool_descriptions.py` / `test_server_instructions.py` may read docs).
- If README cannot be updated without adding lines, write one line to `pr_info/.blocked.txt` and
  stop.
