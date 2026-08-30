# MCP Workspace — LLM Test Plan

Each test below is self-contained and can be run independently. Execute the steps by calling the MCP tools listed.

If you find any issues — wrong results, confusing errors, broken output formatting — report them.

---

## Section 1: Local file & search tools

### Test 1.1: Save / read / append / search / delete

1. `save_file("_test.txt", "line one\nline two\n")`
2. `read_file("_test.txt")` — expect `"line one\nline two\n"`
3. `append_file("_test.txt", "line three\n")`
4. `read_file("_test.txt")` — expect all three lines
5. `search_files(glob="_test.txt")` — expect one match
6. `delete_this_file("_test.txt")`
7. `search_files(glob="_test.txt")` — expect zero matches

### Test 1.2: Basic text replacement + already-applied path

1. `save_file("_test.txt", "Hello world\nThis is a test\n")`
2. `edit_file("_test.txt", old_string="Hello world", new_string="Greetings earth")`
3. `read_file("_test.txt")` — expect `"Greetings earth\nThis is a test\n"`
4. `edit_file("_test.txt", old_string="Hello world", new_string="Greetings earth")` — expect `"No changes needed - edit already applied"`
5. `delete_this_file("_test.txt")`

### Test 1.3: Two sequential edits

1. `save_file("_test.txt", "First section\nSecond section\nThird section\nFourth section\n")`
2. `edit_file("_test.txt", old_string="First section", new_string="Section one")`
3. `edit_file("_test.txt", old_string="Third section", new_string="Section three")`
4. `read_file("_test.txt")` — expect both replacements present
5. `delete_this_file("_test.txt")`

### Test 1.4: Indentation preserved

1. `save_file("_test.py", "def example():\n    # comment\n    x = 5\n    return x\n")`
2. `edit_file("_test.py", old_string="# comment", new_string="# returns five")`
3. `read_file("_test.py")` — expect 4-space indentation preserved
4. `delete_this_file("_test.py")`

### Test 1.5: Failed match

1. `save_file("_test.txt", "Some content\n")`
2. `edit_file("_test.txt", old_string="does not exist", new_string="x")` — expect clean error
3. `read_file("_test.txt")` — expect unchanged
4. `delete_this_file("_test.txt")`

### Test 1.6: Regex special chars treated as literal

1. `save_file("_test.txt", "(parens) [brackets] *stars* ^anchors$\n")`
2. `edit_file("_test.txt", old_string="(parens) [brackets]", new_string="<angle>")`
3. `read_file("_test.txt")` — expect literal replacement (no regex interpretation)
4. `delete_this_file("_test.txt")`

### Test 1.7: Multi-line edit

1. `save_file("_test.txt", "L1\nL2\nL3\nL4\nL5\n")`
2. `edit_file("_test.txt", old_string="L2\nL3\nL4", new_string="X\nY\nZ")`
3. `read_file("_test.txt")` — expect `"L1\nX\nY\nZ\nL5\n"`
4. `delete_this_file("_test.txt")`

### Test 1.8: Markdown bullet indentation

1. `save_file("_test.md", "- top\n- options:\n- a: 1\n- b: 2\n")`
2. `edit_file("_test.md", old_string="- options:\n- a: 1\n- b: 2", new_string="- options:\n  - a: 1\n  - b: 2")`
3. `read_file("_test.md")` — expect nested bullets indented
4. `delete_this_file("_test.md")`

### Test 1.9: Multi-match safety + replace_all

1. `save_file("_test.txt", "foo bar foo baz foo\n")`
2. `edit_file("_test.txt", old_string="foo", new_string="FOO")` — expect error containing `"Multiple matches (3) found for foo"` and the hint `"Use replace_all=True"`
3. `edit_file("_test.txt", old_string="foo", new_string="FOO", replace_all=True)`
4. `read_file("_test.txt")` — expect `"FOO bar FOO baz FOO\n"`
5. `delete_this_file("_test.txt")`

### Test 1.10: move_file

1. `save_file("_a.txt", "content\n")`
2. `move_file("_a.txt", "_b.txt")`
3. `read_file("_b.txt")` — expect `"content\n"`
4. `search_files(glob="_a.txt")` — expect zero matches
5. `save_file("_target.txt", "exists\n")`
6. `move_file("_b.txt", "_target.txt")` — expect error message exactly `"Destination already exists"`
7. `move_file("_does_not_exist.txt", "_x.txt")` — expect error message exactly `"File not found"`
8. Cleanup both remaining files

### Test 1.11: Search, listing, sliced reads, file-size check

1. `list_directory()` — expect file list scoped to project, gitignored paths excluded
2. `list_directory(dirs_only=True)` — expect only directory entries, each with trailing `/`
3. `search_files(pattern="def main", glob="**/*.py")` — expect content matches with file paths and line numbers
4. `search_files(pattern="[unclosed")` — invalid regex; expect literal-text fallback with note containing `"Pattern treated as literal text (invalid regex)"`
5. `save_file("_slice.txt", "line one\nline two\nline three\nline four\nline five\n")`
6. `read_file("_slice.txt", start_line=2, end_line=4)` — expect lines 2-4 with line-number prefixes using the Unicode arrow `→` (U+2192), not `:` or `|` (e.g. `"2→line two\n3→line three\n4→line four\n"`)
7. `delete_this_file("_slice.txt")`
8. `check_file_size(max_lines=10000)` — expect output starting with `"File size check passed"` and mentioning the total file count. May also surface a `"Stale allowlist entries"` section — both are normal.

### Test 1.12: Reference-project tools

Skip the whole test if `get_reference_projects()` returns `count: 0`.

1. `get_reference_projects()` — expect dict with `count` (int), `projects` (list of `{name, url}` objects), `usage` (str)
2. Pick a project name from step 1's output.
3. `list_reference_directory(reference_name=<name>)` — expect file/dir listing
4. Pick a known file from step 3 (e.g. `README.md`).
5. `read_reference_file(reference_name=<name>, file_path=<file>)` — expect file content
6. `search_reference_files(reference_name=<name>, glob="**/*.py")` — expect matches (skip step if project has no Python)

---

## Section 2: Local git tools

(No network. Read-only. **Skip Test 2.1 step 8 if the repo has fewer than 2 commits.**)

### Test 2.1

1. `get_base_branch()` — expect a non-empty string (may be the parent branch, not necessarily `"main"`)
2. `git(command="status")` — expect output containing `"On branch"` and a working-tree state line
3. `git(command="log", max_lines=100)` — expect output starting with `"commit "` and containing `"Author:"`
4. `git(command="branch", args=["--show-current"])` — expect current branch name (non-empty)
5. `git(command="rev_parse", args=["HEAD"])` — expect a 40-char SHA
6. `git(command="ls_files", args=["src/"])` — expect tracked files under `src/`
7. `git(command="diff", args=["HEAD", "--stat"], compact=False)` — on a clean tree expect literal `"No changes found"`; otherwise expect a file-change summary
8. `git(command="diff", args=["HEAD~1..HEAD", "--stat"], compact=False)` — expect file-change summary for the latest commit (**requires ≥2 commits**)

---

## Section 3: Network-bound tools (slow, rate-limited)

These hit live APIs. Run only when needed.

### Test 3.1

1. `github_issue_list(state="open", max_results=3)` — expect lines starting with `#` (e.g. `"#200 [open] ..."`)
2. `github_search(query="bug", max_results=3)` — expect issue results only (`is:issue` is the default), no auto-filter note
3. Pick an issue number from step 1.
4. `github_issue_view(number=<from step 1>)` — expect formatted issue body
5. `github_search(query="is:pr is:closed", max_results=3)` — expect `[PR]` lines only; pick a closed PR number (or skip if none)
6. `github_pr_view(number=<from step 5>)` — expect formatted PR body
7. Pick a reference project `<name>` from `get_reference_projects()`. Skip steps 8-10 if it returns `count: 0` or the chosen project has a null `url`.
8. `github_issue_list(reference_name=<name>, state="open", max_results=3)` — expect lines starting with `#`, from the sibling repo
9. `github_issue_view(number=<from step 8>, reference_name=<name>)` — expect formatted issue body
10. `github_issue_list(reference_name="does_not_exist")` — expect exactly `"Error: Reference project 'does_not_exist' not found"`

### Test 3.2

1. `check_branch_status(ci_timeout=0, pr_timeout=0)` — with polling disabled, returns immediately. Expect output containing each of these line prefixes:
   - `"Branch:"`
   - `"Branch Status:"`
   - `"GitHub Label:"`
   - `"Recommendations:"`

---

## Section 4: GitHub write tools (MUTATING — opt-in)

**These tools create and modify real GitHub objects.** Run only when you intend
to write to the repository. GitHub has no issue-delete API, so the test issue is
closed rather than removed.

### Test 4.1: Issue create → edit → comment → close

1. `github_label_list()` — expect one line per label with name, `#color` and description
2. `github_label_list(search="bug")` — expect the filtered subset
3. `github_issue_create(title="LLM test - safe to close", body="Created by tests/LLM_Test.md Section 4.")` — expect `Created issue #N — <url>`, then `Labels: (none)` and `Assignees: (none)`
4. `github_issue_comment(number=<N from step 3>, body="Test comment.\nSecond line.")` — expect `Added comment to issue #N — <url>`
5. `github_issue_edit(number=<N>, title="LLM test - edited", add_labels=["<a real label from step 1>"])` — expect `Updated issue #N`, then a `Labels:` line containing that label
6. `github_issue_edit(number=<N>, remove_labels=["<a label NOT on the issue>"])` — expect success, not an error: the no-op removal is filtered out
7. `github_issue_edit(number=<N>, add_labels=["status-01:created"])` — expect an error naming `mcp-coder gh-tool set-status`, and no change to the issue
8. `github_issue_edit(number=<N>, add_labels=["definitely-not-a-real-label"])` — expect an error naming the unknown label
9. `github_issue_edit(number=<N>, state="closed")` — expect `(state: closed)`

### Test 4.2: Cross-repo issue create → comment → edit → close

**Writes to a sibling repository.** Skip the whole test if `get_reference_projects()` returns
`count: 0` or no project has a non-null `url`.

1. Pick a reference project `<name>` with a non-null `url`.
2. `github_label_list(reference_name=<name>)` — expect that repo's labels, one per line
3. `github_issue_create(title="LLM test - safe to close", body="Created by tests/LLM_Test.md Section 4.", reference_name=<name>)` — expect `Created issue #N — <url>`, with the URL pointing at the sibling repo
4. `github_issue_comment(number=<N from step 3>, body="Test comment.", reference_name=<name>)` — expect `Added comment to issue #N — <url>`
5. `github_issue_edit(number=<N>, add_labels=["status-01:created"], reference_name=<name>)` — expect an error naming `mcp-coder gh-tool set-status` and that project's own checkout, and no change to the issue
6. `github_issue_edit(number=<N>, state="closed", reference_name=<name>)` — expect `(state: closed)`

### Test 4.3: PR creation guards (no PR is created)

Only the rejection paths are scripted — creating a real PR needs a real branch.

1. `github_pr_create(title="")` — expect an empty-title error
2. `github_pr_create(title="x", head="main", base="main")` — expect a head/base error
3. `github_pr_create(title="x", head="bad~name")` — expect an invalid-branch-name error
