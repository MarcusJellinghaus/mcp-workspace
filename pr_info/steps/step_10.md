# Step 10 — Docs: rules-file and missing-path notes (gaps 8, 9)

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement **only** `pr_info/steps/step_10.md`.
> This is a docs-only step. Run pylint, pytest (`-n auto`) and mypy to confirm everything still
> passes, and make exactly one commit.

## Goal

Document two existing behaviours of the rules that `docs/file-access.md` doesn't mention yet.

## WHERE

- `docs/file-access.md`

## WHAT

1. **"Built in, not overridable" list, the `.mcp-file-access` bullet:** append
   "A gitignored `.mcp-file-access` with no matching rule stays hidden: the built-in rule caps it
   at read-only, it does not expose it."
2. **"Known differences from git", the "path that does not exist yet" bullet:** append
   "The same holds for `.mcp-file-access` rules: a missing path is matched as a directory, so
   `read-only /cache/` refuses `save_file("cache")` for a file that does not exist yet."

## HOW / ALGORITHM / DATA

None; text only. Both statements describe current code: the built-in branch of
`_access_of_spelling`, and `is_dir = not is_file()` for missing paths.

## Tests

None. The existing suite must pass.

## Final check

Before committing, verify these against the issue's Acceptance list:
- all #404 release-note bullets from steps 1–9 are present;
- `docs/file-access.md` no longer says "Reading a hidden path keeps the gitignore message";
- no `.scratch/` directory exists.

If any bullet or doc change from an earlier step is missing, write one line to
`pr_info/.blocked.txt` naming it and stop.

## Commit

`docs(file-access): document rules-file hiding and missing-path matching (#404)`
