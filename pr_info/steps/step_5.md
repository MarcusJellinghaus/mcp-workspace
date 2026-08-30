# Step 5 — Tool enumeration, documentation, skill and local allowlist

Read [summary.md](./summary.md) first. Depends on steps 1-4 (all four tools accept
`reference_name`).

The code is complete after step 4; what remains is the guidance that still says the write tools
cannot reach a sibling repository. #232 called the tool table and the Bash allowlist "one
statement read from two directions" — a line telling a caller to use `gh` for something the MCP
tool now does is exactly the stale-guidance failure that produced this issue.

## WHERE

- `src/mcp_workspace/server_reference_tools.py` — `usage` string (`:77-81`) and
  `get_reference_projects` docstring (`:47-49`)
- `tests/test_reference_projects_mcp_tools.py` — `:51-64` and `:87-96`
- `README.md` — `:35`, `:88`, `:374`, `:383`, `:454-460`
- `.claude/CLAUDE.md` — the sibling-repos line (`:63`) and the Bash allowlist (`:102-103`)
- `.claude/skills/issue_approve/SKILL.md` — `:26-32` and `:51-59`
- `.claude/settings.local.json` — `permissions.allow`
- `tests/LLM_Test.md` — Section 4

## WHAT

One enumeration, written identically in the `usage` string and in the docstring, now listing all
eight tools that accept `reference_name`: `git()`, `github_issue_view()`,
`github_issue_list()`, `github_pr_view()`, `github_search()`, `github_label_list()`,
`github_issue_create()`, `github_issue_edit()`, `github_issue_comment()` — alongside the three
file tools already named.

## HOW

**Enumeration (production string, three consumers).** Change the `usage` string and the
docstring in `server_reference_tools.py`, then update the two assertions in
`tests/test_reference_projects_mcp_tools.py` that compare it by **exact equality**, and the
verbatim sample at `README.md:383`. These four sites move together in this commit. Do **not**
refactor the list into a shared constant — the exact-equality assertions are deliberate.

**README.**

- `:35` — the feature bullet stops being "Cross-repo GitHub reads"; name the read tools and the
  three write tools plus `github_label_list`.
- `:88` — "Reference projects can only be browsed and read from, never modified" is still true
  of *files* and misleading once sibling issues are writable; qualify it to file access and
  point at the cross-repo GitHub section.
- `:374` — "tells a caller whether the project supports the GitHub read tools"; drop "read".
- `:383` — verbatim usage-string quote, must match byte-for-byte.
- `:454-460` — rewrite the section as one block rather than four separate line edits: retitle
  "Cross-Repo GitHub Reads" → "Cross-Repo GitHub Access", rewrite the intro sentence naming the
  tools, keep the first two feature bullets (URL resolution without cloning; allowlist-only
  names), and replace the reads-only bullet at `:460` — which is flatly false after step 4 —
  with one stating that `github_pr_create` and every other GitHub tool remain workspace-only.
  Keep the Error Handling block as-is; both strings are still exact.

**`.claude/CLAUDE.md`.**

- The "Sibling repos are readable in full…" line: sibling repos are now also writable through
  the issue tools; list them. The tool-mapping table above it does **not** change — this issue
  adds no tool and renames none, and the table lists names only.
- Delete two now-stale Bash allowlist entries: `gh issue view (cross-repo only …)` (obsoleted by
  #255 and not removed at the time) and `gh issue comment (cross-repo only …)` (obsoleted by
  step 2). Everything else in that block stays, including `mcp-coder gh-tool set-status <label>`.

**`.claude/skills/issue_approve/SKILL.md`.**

- `:26-32` (Cross-Repo Issues): name `github_issue_comment` alongside `github_issue_view` as
  reference-project-capable.
- `:51-59`: the sentence "the MCP tool only reaches the current repository" is now false for a
  configured reference project. Split the branch: when `owner/repo` matches the `url` of an
  entry returned by `get_reference_projects()`, comment via
  `mcp__mcp-workspace__github_issue_comment(number=…, body="/approve", reference_name=<name>)`;
  otherwise keep the `MSYS_NO_PATHCONV=1 gh issue comment … --repo owner/repo` fallback, which
  must survive for repos that are not configured reference projects.
- The `allowed-tools` frontmatter (`:5-11`) is **unchanged**: both the MCP tool and the Bash
  fallback are still used. Note the asymmetry deliberately — the skill's own frontmatter is the
  grant for its fallback, while CLAUDE.md's general allowlist line is the stale guidance being
  removed.
- `.claude/agents/issue-approver.md` reads this skill at runtime and inherits the fix; no edit
  there.

**`.claude/settings.local.json`.** Add `"mcp__mcp-workspace__github_label_list"` to
`permissions.allow`, beside the four GitHub read tools. The three write tools stay **off** —
#232's "hidden per-client" position holds for writes; `github_label_list` is a read tool whose
misfiling costs a permission prompt on every label lookup.

**`tests/LLM_Test.md`.** Add a cross-repo script to Section 4 (mutating, opt-in), **not**
Section 3. Keep it short and in the existing numbered style, e.g.: pick a reference project with
a non-null `url`; `github_label_list(reference_name=<name>)`; `github_issue_create(...,
reference_name=<name>)` → `Created issue #N — <url>` pointing at the sibling repo;
`github_issue_comment(number=N, reference_name=<name>)`; `github_issue_edit(number=N,
add_labels=["status-01:created"], reference_name=<name>)` → error naming that project's own
checkout; `github_issue_edit(number=N, state="closed", reference_name=<name>)`.

## ALGORITHM

None — string and prose edits only.

## DATA

The `get_reference_projects()` return shape is unchanged (`count`, `projects`, `usage`); only
the `usage` text grows.

## Tests

`tests/test_reference_projects_mcp_tools.py:51-64` and `:87-96` are updated to the new string in
this commit — they assert by exact equality, so they fail until updated and must not be relaxed
into substring checks. No other test changes; documentation carries none.

Optional but cheap sanity check: `mcp-coder check file-size --max-lines 750` if `README.md` or
`server.py` grew near the threshold.

## LLM prompt

> Implement step 5 of `pr_info/steps/step_5.md`, using `pr_info/steps/summary.md` for context.
> Update the reference-tool enumeration in `src/mcp_workspace/server_reference_tools.py` (both
> the `usage` string and the `get_reference_projects` docstring) to include `github_label_list`,
> `github_issue_create`, `github_issue_edit` and `github_issue_comment`, then update the two
> exact-equality assertions in `tests/test_reference_projects_mcp_tools.py` and the verbatim
> quote in `README.md` so all four sites match byte-for-byte. Do not extract the list into a
> shared constant. Then make the documentation edits listed in the step: `README.md` lines 35,
> 88, 374 and the `454-460` section rewritten as one block; the sibling-repos line in
> `.claude/CLAUDE.md` plus removal of the two stale `gh issue view` / `gh issue comment`
> allowlist entries (leave the tool-mapping table alone); the reference-project branch of
> `.claude/skills/issue_approve/SKILL.md` switched to
> `github_issue_comment(reference_name=…)` while keeping the `gh` fallback and its
> `allowed-tools` entry; `"mcp__mcp-workspace__github_label_list"` added to
> `.claude/settings.local.json` (write tools stay off); and a short cross-repo write script in
> `tests/LLM_Test.md` Section 4. Use the MCP file tools, then run
> `mcp__mcp-tools-py__run_pylint_check`, `mcp__mcp-tools-py__run_pytest_check` (with
> `extra_args: ["-n", "auto", "-m", "not git_integration and not claude_cli_integration and not
> claude_api_integration and not formatter_integration and not github_integration and not
> langchain_integration"]`) and `mcp__mcp-tools-py__run_mypy_check`, and fix everything they
> report. One commit.
