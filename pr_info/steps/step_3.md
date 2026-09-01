# Step 3 — Prose enumerations become category descriptions

One commit, documentation only. Read [summary.md](./summary.md) first.

## WHERE

| File | Line | Current |
|---|---|---|
| `README.md` | 35 | Features bullet listing eight tool names |
| `README.md` | 455 | "Cross-Repo GitHub Access" opening sentence, same eight names |
| `README.md` | 460 | "`reference_name` is accepted by these eight tools alone; ..." |
| `README.md` | 223-229 | Per-tool table — **add seven missing rows**, see below |
| `.claude/CLAUDE.md` | 61 | Sibling-repos paragraph, five read tools plus three write tools |

## WHAT

### `README.md:35`

```markdown
- Cross-repo GitHub access: the GitHub issue, pull request, search and label read tools accept `reference_name`; issues can also be created, edited and commented on
```

### `README.md:455`

```markdown
The GitHub tools that take an optional `reference_name` act on the workspace repository without it, and on the named reference project with it. Issues, pull requests, searches and labels can be read there; issues can also be created, edited and commented on.
```

Keep the read/write distinction — it is the load-bearing fact — but carry it on the
*objects* (issues, PRs, searches, labels) rather than on a list of tool names.

### `README.md:460`

```markdown
- Any GitHub tool without a `reference_name` parameter targets the workspace repository
```

The count goes, and so does the `github_pr_create` example: stating the rule generically
means the sentence stays true if another tool gains the parameter later, which is the
whole point of this issue. The other three bullets in that block (lines 458, 459, 461)
are unchanged.

### `.claude/CLAUDE.md:61`

```markdown
Sibling repos are readable in full via the reference tools, `git` with `reference_name`, and the GitHub read tools with `reference_name` (`get_reference_projects` lists them). Their issues are also writable with `reference_name` — create, edit and comment. Check there before asking about another repo.
```

### `README.md:223-229` — seven rows to add

The per-tool table stops at `github_search`. Seven tools appear in `README.md` **only**
in passages steps 2 and 3 delete, so without these rows they vanish from the README
entirely:

| Tool | Only README mention today | Removed by |
|---|---|---|
| `github_label_list` | lines 35, 383, 455 | steps 2 and 3 |
| `github_issue_create` | lines 35, 383, 455 | steps 2 and 3 |
| `github_issue_edit` | lines 35, 383, 455 | steps 2 and 3 |
| `github_issue_comment` | lines 35, 383, 455 | steps 2 and 3 |
| `search_reference_files` | line 383 only | step 2 |
| `git` | line 383 only | step 2 |
| `github_pr_create` | line 460 only | step 3 |

The last three are not part of the eight-name prose enumeration, but they lose their
last README mention to the same edits. Append after the `github_search` row:

```markdown
| `github_label_list` | Lists the labels defined in a repository | "What labels does this repo use?" |
| `github_issue_create` | Creates a GitHub issue | "Open an issue for the failing import check" |
| `github_issue_edit` | Edits a GitHub issue's title, body or labels | "Retitle issue 12" |
| `github_issue_comment` | Adds a comment to a GitHub issue | "Comment on issue 12 with the repro steps" |
| `github_pr_create` | Creates a GitHub pull request | "Open a PR for this branch" |
| `search_reference_files` | Searches file contents or finds files in a reference project | "Find where the docs project configures logging" |
| `git` | Runs a read-only git command (log, diff, status, show, branch, ...) | "Show the last five commits" |
```

## HOW

No code, no tests, no imports. Prose replacement plus seven table rows.

**The per-tool reference tables keep a row per tool** — that is their purpose, and they
are what makes the category descriptions readable. `README.md:223-229` gains the seven
rows above so every tool that loses its last README mention to steps 2 and 3 is still
named there; the `.claude/CLAUDE.md` tool mapping table already lists all of them and is
unchanged. No existing row in either table is edited or removed.

## DATA

None. No runtime behaviour changes in this step.

## Checks

`run_pytest_check` with `extra_args: ["-n", "auto"]` to confirm nothing regressed;
pylint/mypy/ruff see no changed Python. `run_format_code` before committing, per the
repo's commit rule.

Then grep the two files to confirm the verification bullet holds: no prose passage
outside the reference tables enumerates the GitHub tools that accept `reference_name`,
and no count of them survives.

## LLM prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_3.md`.
>
> Implement step 3: replace the four prose enumerations at `README.md:35`,
> `README.md:455`, `README.md:460` and `.claude/CLAUDE.md:61` with the category
> descriptions given in the step, dropping the "these eight tools alone" count, and
> add the seven missing rows (`github_label_list`, `github_issue_create`,
> `github_issue_edit`, `github_issue_comment`, `github_pr_create`,
> `search_reference_files`, `git`) to the per-tool table at `README.md:223-229`. Leave
> the existing table rows and the `.claude/CLAUDE.md` tool mapping table untouched.
> Afterwards, search both files to confirm no prose passage still lists the GitHub
> tools that accept `reference_name` and no count of them remains.
>
> Use the `mcp__mcp-workspace__*` tools for all file access. Then run
> `run_format_code` and `run_pytest_check` with `extra_args: ["-n", "auto"]`, and
> commit once.
