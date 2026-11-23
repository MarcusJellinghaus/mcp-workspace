# review-implementation review log 1

## Round 1 — 2026-11-23
**Findings**:
Reviewing source diffs for #340 (read paths done; now git tool, context, CLI plumbing, arg validation).Diff reviewed; running the reference-related tests once to confirm they pass before reporting.`src/mcp_workspace/toolset/reference.py:119` — low — `fetch_if_stale` runs before the `try` in `_run_reference_read`, so an unexpected exception on the fetch path (e.g. `Repo()` or `repo.remotes` failing on an unreadable or malformed config inside `has_origin_remote`) fails the read and carries no notes. This contradicts "a fetch failure never fails a read". The same gap exists at `src/mcp_workspace/toolset/git.py` `_run_reference` (the `fetch_if_stale` call is outside the `try`).
`src/mcp_workspace/toolset/reference.py:322` — low — `snap.read_bytes(...)` runs before `read_content` calls `_validate_read_args`, so the error changes at the ref. An empty `file_path` gives `IsADirectoryError("Path '' is not a file")` where today's text is "File path must be a non-empty string". Invalid `start_line`/`end_line` on a missing file report not-found instead of the argument error. Validate the arguments before reading the blob.
`src/mcp_workspace/git_operations/origin_fetch.py:38` — low — `has_origin_remote` repeats `ref_snapshot._open_repo` and `ref_snapshot._has_origin`: the same `Repo(path, search_parent_directories=False)` open, the same `InvalidGitRepositoryError`/`NoSuchPathError` handling and the same origin check. Keep one shared helper in `git_operations` (DRY).
**Decisions**:
Verdict(decision='tasks', tasks=['Move the `fetch_if_stale` call inside the existing `try` (or wrap it in its own `try`) in `_run_reference_read` (src/mcp_workspace/toolset/reference.py:119) and in `_run_reference` (src/mcp_workspace/toolset/git.py). Any unexpected exception on the fetch path, including a `Repo()` or `repo.remotes` failure inside `has_origin_remote`, must then become a note and must not fail the read. Add a test where `has_origin_remote` raises and the read still succeeds and returns the note.', 'In `read_content` (src/mcp_workspace/toolset/reference.py:322), call `_validate_read_args` before `snap.read_bytes(...)`. An empty `file_path` must give "File path must be a non-empty string", and an invalid `start_line`/`end_line` must give the argument error, not not-found, even when the file is missing. Add tests for both cases on the at-ref read path.', 'Remove the duplication between `has_origin_remote` (src/mcp_workspace/git_operations/origin_fetch.py:38) and `ref_snapshot._open_repo`/`ref_snapshot._has_origin`. Keep one shared helper in `git_operations` that opens the repo with `search_parent_directories=False`, handles `InvalidGitRepositoryError`/`NoSuchPathError` and checks for origin, and have both modules use it.'], escalate_reason=None)
**Changes**:
applied

## Round 2 — 2026-11-23
**Findings**:
Round 1 fixes are in. Next I'm checking the rest of the diff: the git tool, search engine, context, clone and CLI plumbing.Checking how `-S`/`-G` values are parsed in short-flag clusters, then the report.NO FINDINGS
**Decisions**:
Verdict(decision='dismiss', tasks=[], escalate_reason=None)
**Changes**:
dismiss
