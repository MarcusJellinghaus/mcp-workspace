# Architecture Guide

This document describes the architectural principles and enforcement tools for the mcp_workspace project.

## Architecture Overview

The project follows a layered architecture pattern:

```
┌──────────────────────────────────────────────────────┐
│  Entry Point (main.py)                               │  ← Application entry
├──────────────────────────────────────────────────────┤
│  MCP Server (server.py)                              │  ← Protocol implementation
├──────────────────────────────────────────────────────┤
│  Toolset (toolset/)                                  │  ← Framework-neutral tool specs
├──────────────────────────────────────────────────────┤
│  checks/                                             │  ← Branch-status checks
├──────────────────────────────────────────────────────┤
│  file_tools/  │  git_operations/  │  github_operations/  │  ← Business logic
├──────────────────────────────────────────────────────┤
│  config  │  constants  │  utils                      │  ← Utilities
├──────────────────────────────────────────────────────┤
│  Shared Libs (mcp_coder_utils)                       │  ← External shared libraries
└──────────────────────────────────────────────────────┘
```

### Layer Responsibilities

| Layer | Purpose | Can Import From |
|-------|---------|-----------------|
| **Entry** | Application startup and initialization | All layers below |
| **Protocol** | Builds a FastMCP server per call from `tool_specs` | Toolset, Tools, Utilities |
| **Toolset** | Defines every tool as a `ToolSpec`, bound to one project directory | checks, Tools, Utilities |
| **checks** | Branch-status checks | Tools, Utilities |
| **Tools (upper)** | file_tools, github_operations | git_operations, Utilities |
| **Tools (lower)** | git_operations | Utilities only |
| **Utilities** | config, constants, utils | N/A (leaf modules) |
| **Shared Libs** | Logging via `mcp_coder_utils` (external package) | N/A (external) |

## Architectural Principles

### 1. Dependency Flow

Dependencies flow **downward** only:
- Entry → Protocol → Toolset → Tools → Utilities
- Higher layers depend on lower layers
- Lower layers never depend on higher layers
- Prevents circular dependencies

### 2. MCP Isolation

MCP protocol concerns are isolated to `server.py`: `create_server` builds a fresh
`FastMCP` and registers every spec from `toolset.tool_specs` through `FastMCPSink`.
`main.py` parses arguments and calls `run_server`; it does not import `mcp`.

The toolset and file tools remain **MCP-agnostic** for:
- Reusability in non-MCP contexts (see [LIBRARY_USE.md](LIBRARY_USE.md))
- Easier testing
- Clearer separation of concerns

### 3. Library Isolation

External libraries are isolated to specific modules:

| Library | Used By | Rationale |
|---------|---------|-----------|
| `mcp` | server.py | Protocol implementation only |
| `git` (GitPython) | git_operations/ | Git functionality isolated |
| `github` (PyGithub) | github_operations/ | GitHub API access isolated |
| `requests` | github_operations/ | HTTP requests isolated |
| `subprocess` | git_operations/verification.py, git_operations/_subprocess_git.py | external binaries; network git with a timeout |
| `truststore` | `_ssl.py`, activated eagerly by `main.py` | OS trust store for GitHub TLS (see below) |
| `structlog` | mcp_coder_utils.log_utils (external) | Logging setup centralized in external package |

### 4. Fast Startup via Lazy Imports

The MCP server is spawned as a fresh OS process on every launch, so import cost
is paid every time (and is amplified on cold start by antivirus file scanning).
PyGithub and GitPython together pull in ~200 extra module files.

To keep startup fast, the heavy libraries are imported **lazily, inside the tool
functions that need them**, rather than at module top level:

- `toolset/` imports `github_operations`, `git_operations`, and the
  branch-status checks inside the tool closures and the helpers they call, so
  building the specs with `tool_specs(...)` loads neither library; they load
  when a git/GitHub tool first runs.
- `file_tools/file_operations.py` imports the git-move helpers inside `move_file`
  only, so the common read/write/edit/list/search path never loads GitPython.
- `reference_projects.py` imports `clone_repo` inside `ensure_available`.

**This is load-bearing, not incidental.** `tests/test_startup_performance.py`
asserts that importing `mcp_workspace.server` does **not** eagerly import
`github`/`git` and that a full process import stays under three seconds;
`tests/toolset/test_toolset_imports.py` asserts that importing the toolset and
calling `tool_specs(...)` loads neither, nor `mcp`. Keep
new imports of these libraries inside function bodies, not at module top level.

These lazy imports do not change the architecture graph: import-linter/tach (via
`grimp`) still see them, and the layering (higher layers may import lower) is
unchanged.

### 5. Truststore Activation (TLS trust)

`truststore.inject_into_ssl()` makes Python's TLS use the OS certificate store
(needed for corporate-proxy CA bundles). It must be active before the **first
Python TLS handshake** — which in this server means any GitHub HTTPS call,
whether via PyGithub or the raw `requests` download in
`github_operations/ci_results_manager.py`. (It is irrelevant to the stdio
transport, `git`, and the `gh` CLI, which don't use Python's `ssl`.)

Activation is eager at the entry point: `main()` calls `ensure_truststore()`
once at startup, after logging and before `run_server()`. This is a single,
design-enforced guarantee owned by the entry point (per `_ssl.py`'s rule that
activation is the application's decision, never an import side effect). It does
not depend on *how* or *whether* any GitHub client is later constructed, and it
covers the raw-`requests` path as well as PyGithub — so individual call sites
never have to remember to activate it.

`ensure_truststore()` is idempotent and cheap; the expensive part of startup
(PyGithub/GitPython, ~530 modules) is deferred via lazy imports — truststore
activation is **not** what made startup slow, so there is no reason to defer it
and trade the guarantee away.

### 6. Forward-Slash Project-Relative Paths

Every project-relative path the server emits is forward-slash separated on every
platform — in structured return values and prose error messages alike. Callers
feed these paths straight back into other tools, so a Windows `src\foo.py` in one
result becomes a mismatch or a doubled prefix in the next call.

**Absolute paths stay native.** `edit_file`'s `File not found: {abs_path}` and
`path_utils._outside_error` keep OS separators: they are not fed back into
tools, and `C:/Users/...` reads worse than it helps.

The rule is enforced at two sources, not per call site:

- `directory_utils._discover_files` — every listing and search tool
  (`list_directory`, `search_files`, and their reference-project variants).
  It takes an optional `skip` callback, called for every entry; `list_files`
  uses it to drop gitignored entries and prune gitignored directories during
  the walk.
- `path_utils.normalize_path` — the relative path returned alongside the
  absolute one.

A new path source belongs next to these, not behind a local `replace("\\", "/")`.

**This is load-bearing.** CI runs on `ubuntu-latest` only, where backslashes never
appear, so CI cannot catch a regression. The guard is
`tests/test_path_separator_invariant.py`, which asserts the invariant across tools.

## Architecture Enforcement Tools

We use three tools to enforce architectural boundaries, and deptry for dependency declarations:

### 1. import-linter

**Purpose:** Contract-based import validation

**Configuration:** `.importlinter`

**What it checks:**
- Layered architecture (dependency flow)
- Library isolation (external dependencies)
- Test independence

**Run:**
```bash
# Windows
tools\lint_imports.bat

# Linux/Mac
./tools/lint_imports.sh
```

### 2. tach

**Purpose:** Module boundary enforcement

**Configuration:** `tach.toml`

**What it checks:**
- Layer dependencies
- Module coupling
- Circular dependency prevention

**Run:**
```bash
# Windows
tools\tach_check.bat

# Linux/Mac
./tools/tach_check.sh
```

### 3. vulture

**Purpose:** Dead code detection

**Configuration:** `vulture_whitelist.py`

**What it checks:**
- Unused functions and classes
- Unused imports
- Unreachable code

**Note:** Some code appears unused but is called dynamically (MCP handlers, pytest fixtures). These are whitelisted in `vulture_whitelist.py`.

**Run:**
```bash
# Windows
tools\vulture_check.bat

# Linux/Mac
./tools/vulture_check.sh
```

### 4. deptry

**Purpose:** Dependency declaration check

**Configuration:** `[tool.deptry]` in `pyproject.toml`

**What it checks:**
- Imports in `src` that are not declared, or only arrive transitively
- Declared runtime dependencies that `src` does not import
- Dev-only packages imported from `src`

**Run:**
```bash
# Windows
tools\deptry_check.bat

# Linux/Mac
./tools/deptry_check.sh
```

## Running All Checks

Run all quality and architecture checks at once:

```bash
# Windows
tools\run_all_checks.bat

# Linux/Mac
./tools/run_all_checks.sh
```

This runs:
1. Code formatting (ruff format, ruff `I`)
2. Linting (ruff)
3. Linting (pylint)
4. Type checking (mypy)
5. Tests (pytest)
6. Import contracts (import-linter)
7. Architecture boundaries (tach)
8. Dead code (vulture)
9. Dependency declarations (deptry)

## CI/CD Integration

`.github/workflows/ci.yml`. These names are the check names a PR reports, so renaming one breaks required status checks.

### Every Push, PR and Dispatch

- `push-checks` matrix: ruff-format, ruff, mypy, no-url-deps, pylint
- file-size
- unit-tests
- git-integration-tests
- check-github-secrets
- github-integration-tests (skipped when `check-github-secrets` finds no credentials)

### PRs Only

- check-forbidden-folders
- `pr-checks` matrix: import-linter, tach, vulture, deptry

**Why PR-only?** Architecture checks are more expensive and are most valuable when reviewing code changes.

### PRs and Pushes to `main`

- coverage: reporting only, never a gate. Runs when unit-tests and git-integration-tests succeeded and github-integration-tests succeeded or was skipped.

## Common Violations and Fixes

### ❌ Circular Import

**Error:**
```
Detected 1 cycle:
  mcp_workspace.file_tools.file_operations
  -> mcp_workspace.file_tools.path_utils
  -> mcp_workspace.file_tools.file_operations
```

**Fix:**
- Move shared functionality to a new module
- Use dependency injection
- Refactor to remove the circular dependency

### ❌ Layer Violation

**Error:**
```
mcp_workspace.file_tools cannot import mcp_workspace.server
(higher layer importing lower layer)
```

**Fix:**
- File tools should not know about the server
- Pass dependencies as function parameters
- Use dependency inversion principle

### ❌ Library Isolation Violation

**Error:**
```
mcp_workspace.file_tools.file_operations imports 'git' directly
(should only be imported by git_operations)
```

**Fix:**
- Use `git_operations.py` functions instead of importing GitPython directly
- Maintains abstraction layer
- Makes testing easier (mock one module, not many)

## File Size Guidelines

Keep files manageable for LLM context windows:

**Maximum recommended:** 750 lines

**If a file exceeds this:**
1. Consider splitting into multiple modules
2. If splitting isn't practical, add to `.large-files-allowlist` with justification
3. Check with: `mcp-coder check file-size --max-lines 750`

## Adding New Modules

When adding new functionality:

1. **Determine the layer** - Where does it belong?
   - Tools? Protocol? Utilities?

2. **Update architecture configs:**
   - Add to `.importlinter` if it introduces new boundaries
   - Add to `tach.toml` if it's a new module

3. **Run architecture checks:**
   ```bash
   tools\run_all_checks.bat  # or .sh
   ```

4. **If a tool is dynamically called** (MCP handler, pytest fixture):
   - Add to `vulture_whitelist.py`

## References

- [Import Linter Documentation](https://import-linter.readthedocs.io/)
- [Tach Documentation](https://docs.gauge.so/tach/)
- [Vulture Documentation](https://github.com/jendrikseipp/vulture)
