# Summary — #404: surface `.mcp-file-access` in tool descriptions, refusals, search output and docs

Step 2 of epic #408. Today an agent rarely learns that `.mcp-file-access` exists. Refusals, tool
descriptions and search output don't mention it, a `.git` path is wrongly blamed on gitignore,
and an invalid rules file goes unnoticed in refusals and search. This change fixes the messages,
descriptions, listing labels and docs. It also adds `verify_file_access` plus a startup warning,
and removes the dead `check_path_not_gitignored`.

Behaviour of the rules themselves does not change: only messages, listing labels, one new search
key, and one new verification function.

## Architectural / design changes

### Refusal wording (one builder per message)

| Case | Message | Built by |
|---|---|---|
| `.git` path | `Security error: Path '<p>' is inside a git directory, which the file tools do not access.` | `path_utils.git_dir_error` (shared by `normalize_path` and `require_access`) |
| Gitignored, workspace | `Path '<p>' is excluded by .gitignore rules and cannot be accessed. The user can expose it with a rule in .mcp-file-access. Use list_directory() to see available files.` | `file_access._excluded_error` |
| Gitignored, reference project | `… The user can expose it with a rule in that project's .mcp-file-access. Use list_reference_directory() to see available files.` | same, `reference=True` |
| Gitignored, rules file invalid | `Path '<p>' is excluded by .gitignore rules and cannot be accessed; .mcp-file-access is invalid (<problems>), so no rule exposes it. Use list_directory() to see available files.` (reference: `that project's …`, `list_reference_directory()`) | same, `problems=rules.problems` |
| Read-only by rule | `No write access to '<p>' (…)` | unchanged |

- **Why it addresses the user:** the hint speaks to the user, not the agent. The MCP tools can't write
  `.mcp-file-access`, and an imperative hint would invite a bypass through native tools.
- **`.git`:** never gets a hint. `_access` now returns a distinguishing reason (`_GIT_DIR`) for
  `.git` paths, so `require_access` can tell `.git` from gitignore. Today both return `(HIDDEN, "")`.
- **Invalid rules file:** the invalid-file text is built from `rules.problems`, never from the `_access`
  reason. So `require_access` on an existing path and `list_accessible_files` on a missing path
  produce identical text, and the message doesn't reveal whether the path exists.
- **Where `_excluded_error` lives:** it moves from `directory_utils` (the gitignore-only layer) to
  `file_access`, because it now knows about the rules file. That is possible once
  `check_path_not_gitignored`, its only other caller, is removed.
- **Message prefixes:** `Path '<p>' is excluded by .gitignore rules` and `No write access to '<p>' (…)`
  stay unchanged. Text is only appended after them.

### Search output

`search_files` (`file_tools/search.py`, used by both search tools) adds a `warning` key, with the
`access_rules_warning` text, only while the rules file is invalid. It is taken from the
`AccessListing.problems` of the listing call the function already makes.

### Listing labels

- **Workspace (`list_directory`):** a gitignored file exposed `read-only` gets the new label
  ` (read-only, not committed)`. Labels are still built in `note()` from the `_NOTE_*` constants.
- **Reference (`list_reference_directory`):** a gitignored file exposed by that project's rules gets
  ` (not committed)`. The data comes from a new defaulted field
  `AccessListing.exposed_ignored: frozenset[str] = frozenset()`, filled at the single point where
  `_exposure_skip` keeps an ignored file. It is not derived by matching the `notes` strings.

### Verification

- **New module `file_tools/verification.py`:** contains `verify_file_access(project_dir) ->
  FileAccessVerification`, which returns a TypedDict with keys `rules_file: CheckResult` and
  `overall_ok: bool`.
  - It mirrors `git_operations/verification.py` and has the same row shape (`ok`, `value`,
    `severity`, optional `error`), so mcp_coder's `_format_section` can render it later.
  - Its only runtime import is `access_rules`. `CheckResult` is imported only under `TYPE_CHECKING`,
    which keeps GitPython from loading and avoids an import cycle with `file_access`.
- **Exports:** at every public-API site, including the lazy `_FILE_ACCESS_EXPORTS` in `directory_utils`.
- **Startup:** `main.py` calls it for the workspace and each existing reference project. The
  existing `_report` logs each problem once.

### LLM-facing text

- One Raises/Returns clause per affected tool.
- One sentence in the server `_INSTRUCTIONS`.
- New phrases are pinned in `tests/test_tool_descriptions.py` and `tests/test_server_instructions.py`.

### Removed

`directory_utils.check_path_not_gitignored`: dead code that ignores the rules, so the new hint
would be wrong there.

## Files

### Created
- `src/mcp_workspace/file_tools/verification.py`
- `tests/file_tools/test_verification.py`

### Modified — source
- `src/mcp_workspace/file_tools/path_utils.py` — `git_dir_error`
- `src/mcp_workspace/file_tools/file_access.py` — `_GIT_DIR`, `require_access`, `_excluded_error` (moved here), labels, `exposed_ignored`, re-exports
- `src/mcp_workspace/file_tools/directory_utils.py` — remove `check_path_not_gitignored`, `_excluded_error`; extend lazy exports
- `src/mcp_workspace/file_tools/search.py` — `warning` key
- `src/mcp_workspace/file_tools/__init__.py` — exports
- `src/mcp_workspace/toolset/read.py` — descriptions, comment
- `src/mcp_workspace/toolset/reference.py` — `reference=True`, labels, descriptions
- `src/mcp_workspace/toolset/write.py`, `toolset/delete.py`, `toolset/move.py` — Raises clauses
- `src/mcp_workspace/server.py` — `_INSTRUCTIONS`
- `src/mcp_workspace/main.py` — startup check
- `vulture_whitelist.py`

### Modified — tests
- `tests/file_tools/test_file_access.py`, `tests/file_tools/test_accessible_listing.py`, `tests/file_tools/test_search.py`
- `tests/test_server.py`, `tests/test_reference_path_rules.py`, `tests/test_file_access_tools.py`
- `tests/test_file_access_listing.py`, `tests/test_tool_descriptions.py`
- `tests/test_server_instructions.py`, `tests/test_main.py`

### Modified — docs
- `docs/file-access.md`, `docs/ARCHITECTURE.md`, `docs/release-notes.md`, `README.md`

## Steps (one commit each)

1. `.git` refusal uses `normalize_path`'s message (5c)
2. Remove `check_path_not_gitignored` (12)
3. Gitignore refusal hint and invalid-file note (5a, 5b, 6)
4. Raises clauses in tool descriptions (1, 2)
5. Server instructions sentence (4)
6. Search `warning` key (3, 7)
7. Workspace label ` (read-only, not committed)` (13a, 13b)
8. Reference label ` (not committed)` (13c)
9. `verify_file_access` and startup warning (11)
10. Docs: rules-file and missing-path notes (8, 9)

Gap 10 (repo `.mcp-file-access` header) is already done on this branch.

## Conventions for every step

- TDD: write or adjust the tests first, then the implementation.
- **Checks:** `run_pylint_check`, `run_pytest_check` (`extra_args=["-n", "auto"]`), `run_mypy_check`
  — all must pass. Run `run_format_code` before committing with `git_commit`.
- Refer to functions by name, not line number.
- **Release notes:** step 1 creates a section
  `## Next minor release — .mcp-file-access surfaced to agents (#404)` at the top of
  `docs/release-notes.md`, and later steps append bullets to it. Earlier sections that quote old
  wordings get a pointer, not a rewrite: append ` Changed in #404, see above.` to the bullet.
- **Blocked precondition:** if a stated precondition does not hold, write one line to
  `pr_info/.blocked.txt` and stop.
