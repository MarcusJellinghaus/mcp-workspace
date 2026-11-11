# Step 14 — Docs: README, LIBRARY_USE, ARCHITECTURE, SECURITY

## LLM prompt

> Read `pr_info/steps/summary.md` and this file. Implement step 14 only (documentation, no code).
> Keep every file under 750 lines. Run pytest (`-n auto`) to confirm nothing references the
> old text, then make exactly one commit.

## WHERE / WHAT

- `README.md` → "Available Tools" table (after the `git` row): one row per tool, short
  description + example prompt, e.g.
  `| git_commit | Commits the given paths or all changes (modifies the repository) | "Commit my changes to src/" |`.
  README is ~733 lines: add only the five rows (no new "Tool Details" sections), stay < 750.
- `docs/LIBRARY_USE.md` → groups table: new row
  `| workspace.git | git_branch, git_branch_delete, git_commit, git_push, git_push_force | no |`;
  update the `read_only` bullet ("`True` for tools that only read") and add one sentence:
  library consumers have no client allowlist, so filter on `spec.read_only` to exclude the
  git-write and GitHub-write tools.
- `docs/ARCHITECTURE.md` → "Library Isolation" table: add
  `| subprocess | git_operations/verification.py, git_operations/_subprocess_git.py | external binaries; network git with a timeout |`.
- `SECURITY.md`:
  - Threat model: an influenced agent can also create/switch branches, commit, push and
    force-push with the user's git credentials.
  - New "Git write tools" restriction list: workspace only; never fetch; push only the current
    branch with a full refspec to `origin`; refuse the default branch and detached HEAD;
    force push only with `--force-with-lease --force-if-includes`; `git_branch_delete` only
    when the tip is on GitHub, never current/default branch, never remote deletion; no amend,
    no `--no-verify`, no reset/clean/checkout of paths.
  - Keep the `git` tool bullets; reword the scope bullet to "the `git` tool changing anything
    beyond what `fetch` updates" (unchanged) and add "a git write tool bypassing its listed
    refusals".
  - Credentials: add `git push` and `git_branch_delete`'s `ls-remote` output to the scrubbed list.

## HOW / ALGORITHM / DATA

Documentation only.

## Commit

`docs: document git write tools`
