# Issue #264 — Move GitHub query construction out of `server.py`

## Goal

Two independent changes, one commit each:

1. **Extract** validation and query construction from the `github_search` MCP handler into a
   new `github_operations/search.py`. Execution stays in `server.py`.
2. **Secondary:** set `exclude_type_checking_imports = True` in `.importlinter` and drop the
   two `base_branch` waivers.

Neither changes behaviour. Every query string and error message stays byte-identical.

## Architectural / design changes

### Layering (step 1)

`docs/ARCHITECTURE.md` §2 reserves `server.py` for tool registration and handlers; every
other GitHub tool delegates to `github_operations/`. Today `github_search` holds ~165 lines,
of which ~60 are GitHub domain knowledge expressed as string literals and regexes: the
`is:issue` default and its five suppression spellings, the `state` vocabulary, label quoting
and validation, assignee validation, and the `type:pull-request` rejection.

Import-linter, tach and pycycle all pass on this file — they govern imports, and this handler
imports nothing forbidden. Domain knowledge as string literals is invisible to import
analysis. **This is not a broken contract; it is a layering fix.**

After: `search.py` owns the domain rules, `server.py` owns the MCP contract (the 43-line tool
docstring) and the execution block.

### Two-phase API, not one function

```python
spec = SearchSpec.from_arguments(query, state, labels, assignee)   # validates, no repo needed
query_string = spec.to_query(repo.full_name)                       # assembles, needs the repo
```

The split is forced by an ordering guarantee: **validation must complete before the manager is
constructed**, so a bad argument never costs a network round-trip. A single
`build_query(repo_full_name, ...)` function cannot do that — it needs `repo.full_name` up
front. Five existing tests assert `_get_repository.assert_not_called()`.

A *validating constructor* rather than two loose functions: the only way to obtain a
`SearchSpec` is through `from_arguments`, so a query cannot be built from unvalidated input.
Precedent: `RepoIdentifier.from_repo_url` (`utils/repo_identifier.py`).

A module with a spec type, **not a `SearchManager`**: a manager class would need a
`_search_manager()` helper mirroring `_issue_manager` and a widened `_repo_access_error`
signature, for one call site.

### Error channel

`from_arguments` raises plain `ValueError` carrying today's message **minus the `Error: `
prefix**. The handler's existing `except Exception as e: return f"Error: {e}"` renders it
unchanged. A custom exception type would have no reader.

Consequence: validation now sits *inside* the `try`, so a genuine bug in `from_arguments`
surfaces as `Error: ...` rather than a traceback — already true of everything else in that
block.

### Import discipline

`github_operations/__init__.py` eagerly imports `base_manager` → PyGithub, and
`tests/test_startup_performance.py` asserts that importing `server` does not pull in
`github`. `search.py` itself imports no PyGithub, but the *import statement in `server.py`*
must stay inside the handler body, next to the existing `format_search_results` import.

`SearchSpec` is imported from the submodule and **never re-exported from
`github_operations/__init__.py`** — that file is on the eager path. `formatters` is the
precedent.

**No `tach.toml` entry.** `tach.toml` sets `exact = false` and already declares
`mcp_workspace.github_operations`, so submodules are covered. A separate `[[modules]]` entry
would need its own `depends_on` and force the parent to declare a dependency on it.
`docs/ARCHITECTURE.md` §"Adding New Modules" says to add new modules to `tach.toml` and is
misleading here; the doc is left unchanged (out of scope).

### Test layering

Today the `github_search` unit tests reach through `server.py` to a mocked
`manager._github_client` to observe the query string, because there is no unit under test
smaller than the MCP handler. After the extraction there is one, and the pure tests need no
`@patch` at all.

- New `tests/github_operations/test_search.py` — pure `SearchSpec` tests, no mocks anywhere.
  Matches `test_labels_manager.py` ↔ `labels_manager.py`.
- `test_github_search_tool.py` keeps the handler-level tests, one validation test as the
  ordering guard, and the three live `@pytest.mark.github_integration` tests.

### Secondary: import-linter and `TYPE_CHECKING` (step 2)

`.importlinter`'s layered contract carries two waivers for
`git_operations.base_branch -> github_operations.{issues,pr_manager}`. They read as waived
layering violations, but the code is already correct: both imports sit inside
`if TYPE_CHECKING:` and exist only to annotate injected optional arguments.
`detect_base_branch` skips the corresponding step when those managers are `None`. There is no
runtime upward dependency.

The waivers exist because the two tools disagree: `tach.toml` sets
`ignore_type_checking_imports = true`, while import-linter counts `TYPE_CHECKING` imports as
real. Setting `exclude_type_checking_imports = True` makes import-linter agree with tach
instead of explaining the disagreement away.

## Invariants — must not change

| Invariant | Why |
|---|---|
| Error strings byte-identical | Several tests compare the whole string |
| `from_arguments` is the **first** statement inside the `try`, before `_issue_manager` | Five tests assert `_get_repository.assert_not_called()`; `test_github_read_tools_reference.py` expects `_issue_manager`'s own error for a valid-argument call |
| `" ".join(p for p in parts if p)` keeps the `if p` filter | Load-bearing: `query=""` must yield `repo:owner/repo is:issue` with no double or trailing space |
| `format_search_results` gets `total_count=None` whenever `items` is empty | It uses that to tell a zero cap apart from a genuine no-match render |
| `search.py` imported inside the handler body, never at module top level | `github_operations/__init__.py` is on the eager PyGithub path |
| The 43-line tool docstring stays on the handler, unduplicated | It is the MCP tool description |
| Execution block unchanged | `search_issues` call, `islice` cap, item dicts, `totalCount` rationale comment |

## Out of scope

The `is:issue` default and its five suppression spellings were settled during #254's
implementation (PR #266 — a live probe found GitHub 422s a query naming no result type). They
move as-is. Also unchanged: PR-only and negated qualifiers being documented rather than coded,
`sort`/`order` staying unvalidated, `docs/ARCHITECTURE.md`, `tach.toml`,
`.large-files-allowlist`, `vulture_whitelist.py`, `github_operations/__init__.py`,
`tests/github_operations/test_github_read_tools_pr_search.py` and
`test_github_read_tools_reference.py`.

## Files created / modified

### Step 1 — extraction

| Path | Action |
|---|---|
| `src/mcp_workspace/github_operations/search.py` | **create** — `SearchSpec` dataclass, ~90 lines |
| `tests/github_operations/test_search.py` | **create** — pure tests, no `@patch` |
| `src/mcp_workspace/server.py` | **modify** — rewrite `github_search` body; drop `import re` (line 5) |
| `tests/github_operations/test_github_search_tool.py` | **modify** — remove 15 tests, update module docstring |

### Step 2 — import-linter

| Path | Action |
|---|---|
| `.importlinter` | **modify** — add `exclude_type_checking_imports = True`; delete both `ignore_imports` lines from the layered contract |

### Untouched

`tach.toml`, `docs/ARCHITECTURE.md`, `.large-files-allowlist`, `vulture_whitelist.py`,
`src/mcp_workspace/github_operations/__init__.py`,
`tests/github_operations/test_github_read_tools_pr_search.py`,
`tests/github_operations/test_github_read_tools_reference.py`.

## Steps

| Step | Commit | File |
|---|---|---|
| 1 | `refactor(github_search): extract SearchSpec into github_operations` | `step_1.md` |
| 2 | `chore(importlinter): exclude TYPE_CHECKING imports, drop base_branch waivers` | `step_2.md` |

Step 1 is a single commit even though it touches four files: splitting it would leave an
intermediate commit where `search.py` is dead code (vulture fails) or where the handler and
its extracted module both hold the same logic. Step 2 is independent of step 1 and could be
committed in either order.

## Checks

Run after each step:

```
mcp__mcp-tools-py__run_format_code          # before staging
mcp__mcp-tools-py__run_pylint_check
mcp__mcp-tools-py__run_pytest_check         # extra_args: ["-n", "auto"]
mcp__mcp-tools-py__run_mypy_check
mcp__mcp-tools-py__run_vulture_check
mcp__mcp-tools-py__run_ruff_check
mcp__mcp-tools-py__run_lint_imports_check
mcp__mcp-tools-py__run_tach_check
```

The last four matter here specifically: vulture catches the now-unused `import re`, and
lint-imports/tach are the subject of step 2.
