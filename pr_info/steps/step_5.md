# Step 5 — Documentation and release notes

## LLM prompt

> Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_5.md`). Steps 1–4 are
> done. Implement **only** this step: documentation and one tool description. Keep the
> surrounding style and length; follow the Writing style section of `.claude/CLAUDE.md`.
> Run pylint, pytest (`-n auto`) and mypy; all must pass. Format, then make exactly one commit.

## WHERE / WHAT

| File | Change |
|---|---|
| `README.md` ~line 40 ("Gitignored paths") | Rules come from every `.gitignore` from the project root down plus `.git/info/exclude` (worktrees and submodules included), with git's precedence; global excludes are not read. Reference projects apply their own rules the same way. |
| `README.md` ~line 41 ("Listing a subdirectory") | Replace: listing an ignored directory is refused; a directory whose files are all ignored lists as empty. |
| `README.md` ~line 405 (List Directory details) | Same rule set as the other tools; ignored directories are refused and never descended. |
| `README.md` ~line 666 (`check_file_size`) | "excluding `.git/` and anything the gitignore rules match"; drop "Nested `.gitignore` files are not read". |
| `README.md`, next to the gitignore bullets | Known differences from git: `project_dir` is the root (no `.gitignore` above it, not the enclosing repo's `info/exclude`); a nested repository or submodule checkout inside `project_dir` gets the outer rules and its own `info/exclude` is not read; ignore rules apply to committed files too; global excludes are not applied; a not-yet-existing `out` under rule `out/` is refused. |
| `SECURITY.md` line 30 | "paths matched by that project's gitignore rules"; drop the listing exception sentence. |
| `SECURITY.md` line 31 | "Any `.gitignore` is writable, so an agent that edits one changes which paths are refused." |
| `SECURITY.md` line 75 | "editing any `.gitignore` to lift its rules". |
| `docs/ARCHITECTURE.md` ~line 137 | `_discover_files` takes an optional `skip` callback, called for every entry; `list_files` uses it to drop gitignored entries and prune gitignored directories during the walk. |
| `docs/processes-prompts/refactoring-guide.md` line 104 | "anything the project-root `.gitignore` matches" → "anything the gitignore rules match". |
| `src/mcp_workspace/toolset/checks.py` lines 57–59 (`check_file_size` docstring = tool description) | "excluding `.git/` and anything the gitignore rules (every `.gitignore` and `.git/info/exclude`) match." Drop the "Nested" sentence. |
| `docs/release-notes.md` | New top section `## Next minor release — gitignore rules follow git (#392)` with bullets: nested `.gitignore` + `info/exclude` now applied by every tool; `list_directory` refuses ignored directories; new error wording `Path '<p>' is excluded by .gitignore rules …`; `read_gitignore_rules`, `apply_gitignore_filter`, `filter_with_gitignore` removed (signatures of `is_path_gitignored`, `check_path_not_gitignored`, `list_files` unchanged; `list_files` returns `[]` for an ignored directory); igittigitt `>=2.4.0`. |

## HOW

- Search for leftovers before committing: `search_files(pattern="root `?\\.gitignore|Nested `?\\.gitignore|info/exclude")`
  and fix any remaining statement that the root file is the only rule source.
- No behaviour change in this step.

## ALGORITHM / DATA

None.

## Commit

`docs: describe git-conformant gitignore rules (#392)`
