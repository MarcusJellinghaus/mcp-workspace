# Summary — #373: `renormalize_paths` and `is_staged_diff_cr_only`

## Goal

mcp-coder (MarcusJellinghaus/mcp_coder#1266) needs to clear a working tree whose only changes
are line endings: a file committed with CRLF that is now under a `text` attribute in
`.gitattributes`, so it always shows as modified. Two helpers are added to `git_operations`:

- `renormalize_paths(paths, project_dir) -> GitResult` runs `git add --renormalize -- <paths>`.
- `is_staged_diff_cr_only(paths, project_dir) -> bool` runs
  `git diff --cached --ignore-cr-at-eol --quiet -- <paths>`.

The full specification is issue #373. This plan follows it and does not repeat it.

## Architectural / design changes

- **`_chunk_paths` moves from `staging.py` to `core.py`.** `staging` imports from
  `repository_status`, so `repository_status` cannot import from `staging`. `core` is the shared
  base that both already import. `staging` imports `_chunk_paths` by name, so the patch target
  `mcp_workspace.git_operations.staging._chunk_paths` in `test_unstage_paths.py` still works.
- **`renormalize_paths` follows the pattern of `unstage_paths`:**
  - It opens the repo with `safe_repo_context`, converts paths with `to_git_paths` and runs one
    `run_git_raw(..., literal_paths=True)` call per `_chunk_paths` chunk.
  - It returns a `GitResult` and catches only `InvalidGitRepositoryError` / `NoSuchPathError`.
- **`is_staged_diff_cr_only` is a fail-closed yes/no query.** It uses the same building blocks,
  wrapped in one `except Exception`, and returns `False` on any error. It does not copy
  `has_staged_changes`, which raises.
- **Empty `paths` never reaches git.** With no pathspec, the git command would act on the whole
  repo or the whole index. The repo is still opened first, so an empty list on a non-repo fails.
- **No new types and no changes to the MCP tool layer.** The `git_diff` allowlist is unchanged.
- **The public API grows by two names:** `mcp_workspace.git_operations.__all__` goes from 68 to
  70 entries. Each function also stays importable from its submodule, because mcp-coder's shim
  imports from the submodules.

## Test design (KISS)

- One shared `crlf_repo` fixture in `tests/git_operations/conftest.py`:
  1. Uses the `git_repo` fixture and sets `core.autocrlf=false`.
  2. Commits `doc.md` with CRLF endings.
  3. Writes an untracked `.gitattributes` containing `*.md text`.
  4. Rewrites `doc.md` so the stat cache cannot hide the change.
- All tests use real git with `@pytest.mark.git_integration`. There are no mocks.
- "No git call for empty `paths`" is shown by an observable effect, not a mock: a git call
  without a pathspec would have staged or flagged something.
- Failure cases (non-repo with `[]`, non-repo with a path, path outside the project) are
  parametrized.
- No separate import tests. Each test file imports from the submodule, and
  `test_init_exports.py` covers the package exports.

## Files

| Action | Path |
|---|---|
| modify | `src/mcp_workspace/git_operations/core.py` — gains `_chunk_paths` |
| modify | `src/mcp_workspace/git_operations/staging.py` — loses `_chunk_paths`, gains `renormalize_paths` |
| modify | `src/mcp_workspace/git_operations/repository_status.py` — gains `is_staged_diff_cr_only` |
| modify | `src/mcp_workspace/git_operations/__init__.py` — two new exports |
| modify | `tests/git_operations/test_staging.py` — `_chunk_paths` import from `core` |
| modify | `tests/git_operations/conftest.py` — `crlf_repo` fixture |
| modify | `tests/git_operations/test_init_exports.py` — count 68 → 69 → 70 |
| create | `tests/git_operations/test_renormalize_paths.py` |
| create | `tests/git_operations/test_is_staged_diff_cr_only.py` |
| modify | `docs/release-notes.md` — new section for #373 |

## Steps

1. Move `_chunk_paths` to `core.py` (refactor, no behaviour change).
2. `crlf_repo` fixture + `renormalize_paths` + export + release note.
3. `is_staged_diff_cr_only` + export + release note.

Each step is one commit, with format, pylint, pytest (`-n auto`), mypy and lint-imports passing.
