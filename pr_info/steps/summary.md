# Summary — stage_specific_files bypasses git line-ending normalization (#326)

## Problem

`stage_specific_files` stages files with GitPython's `repo.index.add(...)`, a pure-Python
reimplementation that writes raw working-tree bytes as the blob — it runs no clean filters
and ignores `.gitattributes`. On Windows with `autocrlf`, a CRLF working-tree file is
committed as a CRLF blob even under `* text=auto`. The sibling function `stage_all_changes`
already uses `repo.git.add("--all")` (real git), so the two staging paths disagree on the
same file, producing alternating CRLF/LF blobs in history that later break `git rebase`.

## Architectural / design change

- **Staging moves from the GitPython index API to real git**, for `stage_specific_files`
  only. This aligns it with `stage_all_changes` (already porcelain) and `commits.py`
  (already porcelain, for the same root-cause reason — see its docstring). After this
  change, `git_operations/staging.py` has no remaining `repo.index.add` call; `repo.index.*`
  is only ever used for reads elsewhere in the module.
- **New private helper `_chunk_paths`** splits a path list into git-command-line-safe
  chunks by total character length. It is pure and repo-independent, so it is unit-tested
  without a git fixture — a small, separately testable unit.
- **Literal pathspecs via environment, not a CLI flag.** `repo.git.add` interprets `[`, `*`,
  `:(magic)` as pathspec patterns, which `index.add` never did. `GIT_LITERAL_PATHSPECS=1` is
  set through `repo.git.custom_environment(...)` — the same context-manager pattern already
  used in `diffs.py` for `LC_ALL`, applied here unconditionally (not gated on OS).
- **Behavioural contract change, documented in the docstring:** staging is no longer
  all-or-nothing. `git add` refuses ignored paths (where `index.add` silently staged them);
  a `False` return can now leave some files staged within the failing chunk, and chunks
  before a failing one stay staged. Staging is idempotent, so a retry after a `False` is
  safe. Validation (path exists, path inside project) still happens up front and still
  aborts with nothing staged — only the git-add phase can be partial.
- No change to `stage_all_changes`, `commits.py`, or the public signature of
  `stage_specific_files`.

## Files / modules touched

| Path | Change |
|---|---|
| `src/mcp_workspace/git_operations/staging.py` | Modified — add `_chunk_paths`; rewrite `stage_specific_files` body, docstring, and inline comment |
| `tests/git_operations/test_staging.py` | Modified — add `_chunk_paths` unit tests and new staging-behaviour tests (CRLF normalization, equivalence with `stage_all_changes`, literal pathspec, partial staging with an ignored path) |

No new files or modules are created. No change to `__init__.py` exports — `_chunk_paths`
stays private.

## Steps

1. `step_1.md` — `_chunk_paths` helper, TDD, unit-tested standalone.
2. `step_2.md` — Switch `stage_specific_files` to chunked `repo.git.add`; full behavioural
   test coverage (CRLF→LF, equivalence, literal pathspec, partial staging).

## References

- Issue: https://github.com/MarcusJellinghaus/mcp-workspace/issues/326
- Precedents: `src/mcp_workspace/git_operations/commits.py` (porcelain for signing/hooks),
  `src/mcp_workspace/git_operations/diffs.py` (`custom_environment` pattern)
