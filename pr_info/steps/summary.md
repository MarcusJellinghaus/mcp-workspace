# Issue #297 — `list_directory` duplicates the scope prefix in returned paths

## The bug

Windows only. `list_directory(path="docs/architecture")` returns
`docs\architecture/docs/architecture/architecture.md` instead of
`docs/architecture/architecture.md`. The returned strings are not valid paths, so feeding
one back into `read_file` fails and anything pattern-matching on the output is silently
corrupted.

Cause: an unnormalized separator on one side of a `startswith` comparison.

1. `_discover_files` (`file_tools/directory_utils.py:74`) builds entries with native
   separators: `docs\architecture\architecture.md`.
2. `normalize_path` (`file_tools/path_utils.py:118`) returns `str(relative_path)`, also
   native: `docs\architecture`. `server.py:410` passes it as `base_path`.
3. `_build_tree` (`tree_listing.py`) normalizes *the file paths* to `/` but builds
   `strip_prefix` from the un-normalized `base_path`, so `startswith` never matches and
   nothing is stripped.
4. `list_directory_tree` then prepends `render_prefix` to paths that are still full
   project-relative.

On POSIX step 1 already emits `/`, the prefix matches, and the bug does not exist. Every CI
job runs on `ubuntu-latest`, so CI cannot observe this bug or a regression of it.

## The invariant

**Every project-relative path the server emits is forward-slash separated** — in structured
return values and in prose error messages alike.

**Absolute paths stay native.** `edit_file`'s `File not found: {abs_path}` and
`path_utils._outside_error` keep OS separators: they are not fed back into tools, and
`C:/Users/...` reads worse than it helps. This boundary is stated in `docs/ARCHITECTURE.md`
so a later sweep does not re-open it.

## Architectural / design changes

### 1. Two enforcement points, not per-tool output boundaries

Normalization happens at the two places paths are *born*, not at the seven places they are
emitted:

| Enforcement point | Covers |
|---|---|
| `_discover_files` | `list_directory`, `search_files`, `list_reference_directory`, `search_reference_files`, `check_file_size` — the walk never passes through `normalize_path` |
| `normalize_path` | anything derived from a validated path: `delete_directory`'s result list and messages, `move_file`'s returned dict, `list_directory`'s `base_path` |

They are complementary, not alternatives. `normalize_path` alone leaves `_discover_files`
unfixed. Per-site `as_posix()` alone leaves `base_path`, which is a *comparison input*
rather than an emitting site — and it is seven scattered edits, which is exactly how this
bug survived four independent workarounds.

### 2. `base_path` is normalized at the public entry point

`list_directory_tree` normalizes `base_path` once, before it is used both to build
`strip_prefix` and as `render_prefix`. `_build_tree` keeps its existing per-path
`replace("\\", "/")`, so the module is correct for any caller regardless of upstream
convention.

The strip-then-re-add mechanism itself is load-bearing and is **not** changed: `base_path`
is stripped so collapse depth is measured from the scope root, not the project root
(`_find_collapsible` only considers `depth >= 2`). Building the tree from unstripped paths
would change which directories collapse under a scoped listing.

> **Deviation from the issue — ratified, and this section supersedes the issue for these
> two rows.** The issue's Decisions table says to *remove* `_build_tree`'s `replace` as
> "now dead" and to add an aggregated unmatched-prefix warning. Traced through, that does
> not fix the bug for the issue's own first acceptance criterion: given backslash paths
> *and* a backslash `base_path`, `strip_prefix` is `docs\architecture/` while the path is
> `docs\architecture\architecture.md`. They diverge at the separator, `startswith` is still
> False, nothing is stripped, and the output is still a duplicated prefix. Normalizing
> `base_path` instead — one added line rather than one removed and seven added for a
> `logging` import, a counter and a warning — makes that test meaningful and removes the
> warning machinery entirely. With both sides normalized, an unmatched prefix can only mean
> a caller passed a path outside `base_path`, which no caller does (`list_directory_tree`
> has exactly one caller).

Superseded issue items, so no acceptance bullet is left silently unmet:

| Issue item | Disposition here |
|---|---|
| `## Sites` row `tree_listing.py` `_build_tree`: "`replace("\\", "/")` removed (now dead)" | **Not removed.** It is dead for production callers but load-bearing for the regression test, which feeds `_build_tree` backslash paths directly. Replaced by one added line in `list_directory_tree` that normalizes `base_path`. |
| Decisions row "Unstripped-prefix mismatch → log a warning in `_build_tree`" and "Warning granularity → one aggregated warning per call" | **Dropped, not deferred.** With both sides of the `startswith` normalized the mismatch the warning was meant to surface is unreachable from the only caller, so the warning would be unreachable code carrying a `logging` import, a counter and a log line. |
| Acceptance bullet "the normalization workarounds dispositioned as listed in `## Sites`" | Met by the `## Sites` rows as amended above: `search._norm`'s `replace` removed, the three `file_sizes` `replace` calls removed via the retyping, `load_allowlist`'s kept, `_build_tree`'s kept for the reason in row 1. |

Reversing this ratification means restoring the warning (plus the `logging` import) in
`_build_tree`, removing its per-path `replace`, dropping `list_directory_tree`'s
`base_path` normalization, and relaxing the step 1 regression test to forward-slash file
paths with a backslash `base_path`. Nothing else in the plan depends on it.

### 3. `FileMetrics.path` is retyped `Path` → `str`

`check_file_sizes` currently round-trips `list_files`' strings through `Path`, which
*reintroduces* backslashes on Windows, and then three call sites undo it with
`str(x).replace("\\", "/")`. Retyping deletes the round-trip and makes the regression
unexpressible, and it aligns `get_file_metrics` with `list_files`' actual return type.

`load_allowlist` **keeps** its `replace`: it normalizes hand-written allowlist entries,
which are caller input, not server output.

### 4. One parametrized cross-tool invariant test

A single parametrized test over an explicitly named tool set asserts that no returned
string contains a backslash. This is what makes "everywhere" verifiable instead of a list
that drifts, and it is what pins `edit_file`'s compliance, which today is accidental (two
independent `replace` calls). Adding a tool to the guarded set is one line.

It is also the single home for *separator* assertions. Per-tool tests assert only
*correctness* claims that the invariant test cannot express: exact string values, nested
paths, and each path appearing exactly once.

### Tools inventoried

- **Changed:** `list_directory`, `search_files`, `list_reference_directory`,
  `search_reference_files`, `delete_directory`, `_check_not_gitignored`'s error,
  `check_file_size`.
- **Already compliant, pinned by the invariant test:** `edit_file`, `git`,
  `github_pr_view`, `check_branch_status` (GitHub API paths arrive forward-slashed).
- **No path in output:** the remaining GitHub tools, `get_base_branch`,
  `get_reference_projects`, and `move_file`'s MCP tool (returns `bool`, discarding the
  util's dict — so `move_file` is guarded at the util layer).

## Steps

Each step is exactly one commit, leaving pylint/pytest/mypy green.

| Step | Scope |
|---|---|
| 1 | Source normalization and the reported bug: `_discover_files`, `normalize_path`, `list_directory_tree`, `search._norm` |
| 2 | `checks/file_sizes.py` retyping |
| 3 | `delete_directory` children and `_check_not_gitignored` |
| 4 | Cross-tool invariant test (tests only) |
| 5 | `docs/ARCHITECTURE.md` and the `@mcp.tool()` docstrings (docs only) |

**Order: 1 → 3 → 4, with step 2 any time after step 1, and step 5 last.**

- **Step 2 after step 1.** Removing `file_sizes`' `.replace` while `_discover_files` still
  emits backslashes silently breaks allowlist matching on Windows, and Linux-only CI cannot
  catch it. Within a single PR no such state is released, so this is commit ordering rather
  than risk.
- **Step 4 after step 3.** Step 4's invariant test asserts `delete_directory` emits no
  backslash, which only holds once step 3 changes `file_operations.py:458`. Running step 4
  first reds the suite on Windows — the only platform where the bug is observable.
- **Step 5 last**, so the documented invariant matches shipped behaviour.

This matches the preconditions stated in each step's LLM prompt.

## Files created or modified

### Source — modified

| File | Change |
|---|---|
| `src/mcp_workspace/file_tools/directory_utils.py` | `_discover_files` emits `as_posix()`; docstring states the invariant |
| `src/mcp_workspace/file_tools/path_utils.py` | `normalize_path` returns `relative_path.as_posix()` |
| `src/mcp_workspace/file_tools/tree_listing.py` | `list_directory_tree` normalizes `base_path` once |
| `src/mcp_workspace/file_tools/search.py` | `_norm` loses its `replace`; keeps the win32 `.lower()` |
| `src/mcp_workspace/checks/file_sizes.py` | `FileMetrics.path: str`; three `replace` calls and the `Path` round-trip removed |
| `src/mcp_workspace/file_tools/file_operations.py` | `delete_directory` children use `as_posix()` |
| `src/mcp_workspace/server.py` | `_check_not_gitignored` uses `as_posix()`; two tool docstrings (`list_directory`, `search_files`) |
| `src/mcp_workspace/server_reference_tools.py` | two tool docstrings (`list_reference_directory`, `search_reference_files`) |

### Tests — created

| File | Purpose |
|---|---|
| `tests/test_path_separator_invariant.py` | the parametrized cross-tool invariant test |

### Tests — modified

`tests/file_tools/test_tree_listing.py`, `tests/file_tools/test_directory_utils.py`,
`tests/file_tools/test_path_utils.py`, `tests/file_tools/test_search.py`,
`tests/file_tools/test_delete_directory.py`, `tests/file_tools/test_move_operations.py`,
`tests/checks/test_file_sizes.py`, `tests/test_server.py`.

No reference-tool test file is modified: separator coverage for the two reference tools
lives in the new `tests/test_path_separator_invariant.py`, which borrows its fixture pattern
from `tests/test_reference_search_mcp_tools.py` without editing it.

### Docs — modified

`docs/ARCHITECTURE.md`.

### No new folders or modules

The one new file sits in the existing `tests/` root alongside the other cross-cutting
suites (`test_tool_descriptions.py`, `test_startup_performance.py`).
