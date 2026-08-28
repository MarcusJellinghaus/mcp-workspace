# Step 3 — Documentation surfaces

One commit: doc changes + the two test-string updates they force + checks passing.
Read [summary.md](./summary.md) first, in particular design decision 5.

Depends on step 1 only for accurate wording. No production behaviour changes except the
`usage` string, which is itself a documentation surface — it is the discovery path an LLM
follows.

## WHERE

| File | Change |
|---|---|
| `src/mcp_workspace/server_reference_tools.py` | `usage` string in `get_reference_projects()` |
| `tests/test_reference_projects_mcp_tools.py` | Two exact-match assertions that mirror it |
| `README.md` | Reference-project tool surface |
| `.claude/CLAUDE.md` | Sibling-repo line (line 55) |
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

### 2. `tests/test_reference_projects_mcp_tools.py`

Two assertions hardcode the full string (around lines 58 and 86, the 3-project and 1-project
cases). Update both to match exactly. The line-27 assertion
(`"No reference projects available"`) is not affected.

### 3. `README.md`

Three touch points, all short:

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

### 5. `tests/LLM_Test.md`

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
2. Update README.md, .claude/CLAUDE.md line 55, and tests/LLM_Test.md exactly as described
   under WHAT.
3. Run pytest, pylint and mypy until all pass.

Follow the repo writing style: concise, no restating what the reader can already see.
Do not document tools that do not exist — there are no GitHub write tools.

Then run mcp__mcp-tools-py__run_format_code and make exactly one commit.
```

## DONE WHEN

- `get_reference_projects()` names all four GitHub read tools, and its two tests pass.
- All four documentation surfaces from the issue are updated.
- pylint, pytest and mypy are green.
