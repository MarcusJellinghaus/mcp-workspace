# Step 4 — Correct the file-size check scope in `refactoring-guide.md`

Read [summary.md](summary.md) first.

Documentation-only. Single commit. Independent of steps 1, 2 and 3.

## WHERE

`docs/processes-prompts/refactoring-guide.md`, line 104, under the `#### File Size Check` heading.

## WHAT

The line currently reads:

> Verifies all tracked Python files are under the line threshold. If split files were previously in
> `.large-files-allowlist`, remove those entries. Stale entries are reported automatically.

**Wrong on both counts.** The check scans neither only-tracked nor only-Python files. Replace the
first sentence; keep the rest of the paragraph as-is.

Replacement first sentence:

> Verifies every UTF-8 file under the project directory — all file types, tracked or not — is under
> the line threshold, excluding `.git/` and anything the project-root `.gitignore` matches.

## HOW

Note the surrounding context: line 101 is `mcp-coder check file-size --max-lines 750`, so this
paragraph documents the **`mcp-coder` CLI**, not this repo's MCP tool. The correction still belongs
in this repo because the doc lives here, and both implementations scan identically via
`list_files(".", project_dir)` — so one sentence covers both.

This is a doc correction only. It does **not** imply any change to `mcp_coder`'s twin
`checks/file_sizes.py`, which is deliberately left uncapped (see summary.md). Do not mention the
50-item report caps here — they do not apply to the CLI.

Leave the two following sentences untouched:

> If split files were previously in `.large-files-allowlist`, remove those entries. Stale entries
> are reported automatically.

Both are accurate.

## ALGORITHM

None — no executable change.

## DATA

None — no change to return values or data structures.

## TESTS

None. No test asserts on this document.

## CHECKS

No Python changed. Run pytest (`-n auto`) once to confirm the tree is green before committing.

## LLM PROMPT

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_4.md`.
>
> Implement step 4 only: in `docs/processes-prompts/refactoring-guide.md`, replace the first
> sentence of line 104 with the corrected scope sentence given in step_4.md. Keep the two following
> sentences unchanged.
>
> Constraints: do not add anything about the 50-item report caps — that paragraph documents the
> `mcp-coder` CLI, which is not being capped. Do not change any other line, any other file, or any
> Python code.
>
> Then run pytest (`-n auto`) to confirm the tree is green, and commit as
> `docs(refactoring-guide): correct file-size check scope`.
