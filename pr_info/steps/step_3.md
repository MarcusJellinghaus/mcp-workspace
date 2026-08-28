# Step 3 — Documentation surfaces

One commit: doc changes + the two test-string updates they force + checks passing.
Read [summary.md](./summary.md) first, in particular design decision 5.

Depends on step 1 only for accurate wording. No production behaviour changes except the
`usage` string, which is itself a documentation surface — it is the discovery path an LLM
follows.

## WHERE

| File | Change |
|---|---|
| `src/mcp_workspace/server_reference_tools.py` | `usage` string **and** docstring of `get_reference_projects()` |
| `tests/test_reference_projects_mcp_tools.py` | Two exact-match assertions that mirror it |
| `README.md` | Reference-project tool surface, incl. the example `usage` string at line 378 |
| `.claude/CLAUDE.md` | Sibling-repo line (line 55) |
| `.claude/skills/issue_approve/SKILL.md` | Cross-repo section (lines 25-34) |
| `tests/LLM_Test.md` | Manual smoke-test script |

## WHAT

### 1. `usage` string — `server_reference_tools.py`

It enumerates which tools accept a reference name, so it must now list the GitHub read tools:

```python
"usage": (
    f"Use these {len(projects)} projects with list_reference_directory(), "
    f"read_reference_file(), search_reference_files(), git(), "
    f"github_issue_view(), github_issue_list(), github_pr_view(), and github_search()"
),
```

The empty-vault branch (`"No reference projects available"`) is unchanged.

The function's own docstring carries the same enumeration one line shorter and is already
stale (`server_reference_tools.py:47`):

> `Use the returned project names with list_reference_directory() and read_reference_file()`

Update it to the same tool list as the `usage` value above, so the docstring and the returned
string do not disagree:

> `Use the returned project names with list_reference_directory(), read_reference_file(), search_reference_files(), git(), github_issue_view(), github_issue_list(), github_pr_view(), and github_search()`

### 2. `tests/test_reference_projects_mcp_tools.py`

Two assertions hardcode the full string (around lines 58 and 86, the 3-project and 1-project
cases). Update both to match exactly. The line-27 assertion
(`"No reference projects available"`) is not affected.

### 3. `README.md`

Four touch points, all short:

- **Example `usage` string** (line 378, inside the `#### Get Reference Projects` subsection):
  the hardcoded example is already stale and gets staler with this change —
  > `#   "usage": "Use these 3 projects with list_reference_directory() and read_reference_file()"`

  Replace the quoted value with the new `usage` string from §1, so the documented example
  matches what the tool actually returns.
- **Features list** (around lines 32–34): after the `read_reference_file` bullet, add
  > `- Cross-repo GitHub reads: github_issue_view, github_issue_list, github_pr_view and github_search accept reference_name`
- **Available Tools table** (around lines 222–224): add a row
  > `| GitHub read tools with reference_name | Read issues, PRs and search results from a reference project | "Show me issue 12 in the mcp-config project" |`
- **Reference-project subsections of "Tool Details"** (around lines 363–455, after the
  `read_reference_file` subsection): add a short `#### Cross-Repo GitHub Reads` subsection
  stating:
  - the four tool names and that `reference_name` is optional;
  - the repository is resolved from the reference project's **configured URL** — no clone is
    performed, so a URL-only reference project works;
  - only names from `get_reference_projects()` are accepted; arbitrary `owner/repo` strings
    are not;
  - failures are returned as `"Error: ..."` strings, not raised: unknown name, or a reference
    project with no URL configured;
  - reads only — there are no GitHub write tools.

### 4. `.claude/CLAUDE.md` line 55

Currently an undercount:

> Sibling repos are readable in full via the reference tools and `git` with `reference_name`
> (`get_reference_projects` lists them). Check there before asking about another repo.

Replace with:

> Sibling repos are readable in full via the reference tools, `git` with `reference_name`, and
> the GitHub read tools (`github_issue_view`, `github_issue_list`, `github_pr_view`,
> `github_search`) with `reference_name` (`get_reference_projects` lists them). Check there
> before asking about another repo.

Keep it to one paragraph — the file's own writing-style rule.

### 5. `.claude/skills/issue_approve/SKILL.md` lines 25-34

The `## Cross-Repo Issues` section currently routes cross-repo *reads* to `gh` on the grounds
that the MCP tool cannot reach another repo — the exact fallback this issue exists to remove:

> If a `--repo owner/repo` flag was given, append it to every `gh` command below, and fetch the
> issue with `gh issue view <issue_number> --repo owner/repo` via Bash —
> `mcp__mcp-workspace__github_issue_view` only reaches the current repository.

Replace with:

> If a `--repo owner/repo` flag was given, append it to every `gh` command below. Fetch the
> issue with `mcp__mcp-workspace__github_issue_view(<issue_number>, reference_name=<name>)`
> when that repo is a configured reference project (`get_reference_projects` lists them);
> otherwise fall back to `gh issue view <issue_number> --repo owner/repo` via Bash.

Line 34's parenthetical becomes `(or with reference_name for a cross-repo issue)`.

Do **not** change the `gh` calls that label or comment on the issue: those are writes, and
there are no MCP write tools for GitHub. Only the read fallback goes away.

### 6. `tests/LLM_Test.md`

Extend **Test 3.1** (network-bound section) with cross-repo steps, guarded the same way
Test 1.12 is:

```
7. Skip steps 8-10 if `get_reference_projects()` returns `count: 0` or the chosen project has a null `url`.
8. `github_issue_list(reference_name=<name>, state="open", max_results=3)` — expect lines starting with `#`, from the sibling repo
9. `github_issue_view(number=<from step 8>, reference_name=<name>)` — expect formatted issue body
10. `github_issue_list(reference_name="does_not_exist")` — expect exactly `"Error: Reference project 'does_not_exist' not found"`
```

Step 10 is the one that verifies the allowlist actually fails loudly instead of silently
reading the wrong repo.

## ALGORITHM / DATA

None — documentation only, plus one f-string.

## LLM PROMPT

```
Implement step 3 of pr_info/steps/summary.md, specified in pr_info/steps/step_3.md.

Read pr_info/steps/summary.md (especially design decision 5) and pr_info/steps/step_3.md
before starting. Steps 1 and 2 are already committed.

1. Update the usage string in get_reference_projects() in
   src/mcp_workspace/server_reference_tools.py, then update the two exact-match assertions
   in tests/test_reference_projects_mcp_tools.py so they match.
   Update the docstring of get_reference_projects() with the same tool list.
2. Update README.md (including the example usage string at line 378), .claude/CLAUDE.md
   line 55, .claude/skills/issue_approve/SKILL.md lines 25-34, and tests/LLM_Test.md
   exactly as described under WHAT.
3. Run pytest, pylint and mypy until all pass.

Follow the repo writing style: concise, no restating what the reader can already see.
Do not document tools that do not exist — there are no GitHub write tools.

Then run mcp__mcp-tools-py__run_format_code and make exactly one commit.
```

## DONE WHEN

- `get_reference_projects()` names all four GitHub read tools in both its `usage` value and its
  docstring, and its two tests pass.
- All four documentation surfaces from the issue are updated, plus
  `.claude/skills/issue_approve/SKILL.md`.
- No file still states that the GitHub read tools reach only the current repository:
  `grep -r "only reaches the current repository"` returns nothing.
- pylint, pytest and mypy are green.
