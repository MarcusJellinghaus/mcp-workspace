# Step 2 — Switch `stage_specific_files` to chunked `repo.git.add`

Precondition: `_chunk_paths` exists in `src/mcp_workspace/git_operations/staging.py` and its
unit tests pass (step 1 is committed). If it does not exist or its tests fail, write one
line to `pr_info/.blocked.txt` and stop.

## WHERE

- `src/mcp_workspace/git_operations/staging.py` — rewrite the body, docstring, and inline
  comment of `stage_specific_files`. `stage_all_changes` is unchanged (already porcelain).
- `tests/git_operations/test_staging.py` — add a small shared setup helper and four new
  tests.

## WHAT

```python
def stage_specific_files(files: list[Path], project_dir: Path) -> bool:
```

Signature unchanged. Internals: same validation loop (existence, inside-project check,
`_normalize_git_path`) building `relative_paths`, then staging via real git instead of
`repo.index.add`.

## HOW

- After building `relative_paths`, call `_chunk_paths(relative_paths)` (from step 1).
- For each chunk, stage inside `repo.git.custom_environment(GIT_LITERAL_PATHSPECS="1")`
  (same context-manager pattern as `diffs.py`'s `LC_ALL` usage), calling
  `repo.git.add("--", *chunk)`.
- Add a one-line comment directly above the `repo.git.add` call: staging goes through real
  git so clean filters and `.gitattributes` apply — do not use `repo.index.add`.
- `GitCommandError` from any chunk propagates to the existing `except (InvalidGitRepositoryError, GitCommandError)`
  block, which logs and returns `False`. No new exception handling needed.
- Rewrite the docstring: drop the "all-or-nothing" claim. State instead: validation failures
  (missing file, outside project) still return `False` before anything is staged; after
  that, staging happens git-add-chunk by git-add-chunk — a chunk can partially stage valid
  paths and fail only on an ignored one, and a failure in a later chunk leaves earlier
  chunks staged; staging is idempotent, so retrying `stage_specific_files` after a `False`
  is safe; directories are accepted and staged recursively by git.

## ALGORITHM

```
validate each file (exists, inside project) -> relative_paths; return False on first failure
if not files: return True                      # unchanged no-op case
with safe_repo_context(project_dir) as repo:
    for chunk in _chunk_paths(relative_paths):
        with repo.git.custom_environment(GIT_LITERAL_PATHSPECS="1"):
            repo.git.add("--", *chunk)          # real git: filters + .gitattributes apply
    return True
# GitCommandError from any chunk -> caught by existing except block -> False
```

## DATA

- Return value: `bool`, same contract shape as before (`True`/`False`), but see the
  docstring rewrite above for the changed partial-staging semantics on `False`.
- No new data structures. `relative_paths` stays `list[str]`.

## Test additions (one commit, TDD: write failing tests against current `index.add` code
first conceptually — but since this step replaces the implementation in the same commit,
write tests immediately against the target behaviour, run them to confirm they fail against
the still-`index.add` code, then implement)

Add one small non-fixture helper near the top of `test_staging.py` to avoid repeating setup:

```python
def _enable_autocrlf_and_text_attr(repo: Repo, project_dir: Path, pattern: str = "*.md text") -> None:
    with repo.config_writer() as config:
        config.set_value("core", "autocrlf", "true")
    (project_dir / ".gitattributes").write_text(pattern + "\n")
```

Call it with the `git_repo_with_commit` fixture's repo/project_dir before writing test files.
Write test file bytes explicitly (`write_bytes` or `open(..., newline="")`) so CRLF in the
test is never accidental.

1. **`test_stage_specific_files_normalizes_crlf_for_new_file`** — write a new `.md` file with
   explicit `\r\n` line endings, stage it with `stage_specific_files`, read the blob back
   (`repo.git.show(f"HEAD:{path}")` after a commit, or `cat-file`/`ls-files -s` plus
   `cat-file blob`) and assert no `\r` remains. In the same test, reset to a second,
   otherwise-identical repo, stage the same CRLF file with `stage_all_changes` instead, and
   assert the resulting blob is byte-identical to the one from `stage_specific_files` — this
   covers the "new untracked file" equivalence case from the issue in the same test as the
   CRLF assertion.
2. **`test_stage_specific_files_matches_stage_all_for_modified_tracked_file`** — commit an
   `.md` file with LF content first, then in one repo modify it (append a line **and**
   rewrite with CRLF) and stage via `stage_specific_files`; in a second, separately set-up
   repo with the same starting commit, make the identical modification and stage via
   `stage_all_changes`. Assert both staged blobs are identical (and LF). Needs two repos (or
   an equivalent reset) since staging twice in one repo makes the second call a no-op.
3. **`test_stage_specific_files_literal_pathspec_bracket_filename`** — create `a[1].md` and a
   sibling file that the glob pattern `a[1].md` would also match (e.g. `a1.md`), call
   `stage_specific_files([a[1].md path])`, assert only the literal `a[1].md` is staged and
   the sibling stays untracked.
4. **`test_stage_specific_files_partial_staging_with_ignored_path`** — write a `.gitignore`
   ignoring one file, call `stage_specific_files` with a mixed list of one ignored and one
   normal path, assert the return value is `False`, and assert (via `repo.index.diff("HEAD")`
   or equivalent) that the normal file ended up staged and the ignored one did not — this is
   the evidence behind the docstring's partial-staging claim.

## Commit sequence

1. Write the four tests (and the shared helper) against the target behaviour.
2. Run `run_pytest_check` scoped to `test_staging.py`, confirm they fail against the current
   `index.add` implementation (`-v -s --tb=short` for the failure detail).
3. Implement the rewrite in `staging.py` per WHAT/HOW/ALGORITHM above.
4. Re-run the four new tests plus the existing `test_stage_specific_files` /
   `test_stage_all_changes` tests in the file; all must pass.
5. Run `run_format_code`, then `run_pylint_check`, `run_pytest_check` (`-n auto`),
   `run_mypy_check`, `run_ruff_check` across the touched files. All must pass.
6. `git add`, `git commit` (Bash). One commit for this step: tests + implementation
   together.

## LLM prompt for this step

```
Read pr_info/steps/summary.md and pr_info/steps/step_2.md in full before starting.

Implement step_2.md only: rewrite stage_specific_files in
src/mcp_workspace/git_operations/staging.py to stage through chunked repo.git.add calls
instead of repo.index.add, exactly as specified in step_2.md's WHERE/WHAT/HOW/ALGORITHM/DATA
sections, and add the four tests (plus shared setup helper) described there to
tests/git_operations/test_staging.py.

Check the precondition at the top of step_2.md first; if it fails, write one line to
pr_info/.blocked.txt and stop.

Write the tests first against the target behaviour, confirm they fail against the current
index.add implementation, then do the rewrite, then confirm all four new tests plus the
existing staging tests pass. Run run_format_code, run_pylint_check, run_pytest_check
(-n auto), run_mypy_check, run_ruff_check — all must pass. Produce exactly one commit
containing the tests and the implementation together.
```
