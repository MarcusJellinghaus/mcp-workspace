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
| **Protocol** | MCP server implementation and tool registration | Tools, Utilities |
| **Tools (upper)** | file_tools, github_operations | git_operations, Utilities |
| **Tools (lower)** | git_operations | Utilities only |
| **Utilities** | config, constants, utils | N/A (leaf modules) |
| **Shared Libs** | Logging via `mcp_coder_utils` (external package) | N/A (external) |

## Architectural Principles

### 1. Dependency Flow

Dependencies flow **downward** only:
- Entry → Protocol → Tools → Utilities
- Higher layers depend on lower layers
- Lower layers never depend on higher layers
- Prevents circular dependencies

### 2. MCP Isolation

MCP protocol concerns are isolated to:
- `main.py` - Server initialization
- `server.py` - Tool registration and handlers

File tools remain **MCP-agnostic** for:
- Reusability in non-MCP contexts
- Easier testing
- Clearer separation of concerns

### 3. Library Isolation

External libraries are isolated to specific modules:

| Library | Used By | Rationale |
|---------|---------|-----------|
| `mcp` | main.py, server.py | Protocol implementation only |
| `git` (GitPython) | git_operations/ | Git functionality isolated |
| `github` (PyGithub) | github_operations/ | GitHub API access isolated |
| `requests` | github_operations/ | HTTP requests isolated |
| `truststore` | `_ssl.py`, activated eagerly by `main.py` | OS trust store for GitHub TLS (see below) |
| `structlog` | mcp_coder_utils.log_utils (external) | Logging setup centralized in external package |

### 4. Fast Startup via Lazy Imports

The MCP server is spawned as a fresh OS process on every launch, so import cost
is paid every time (and is amplified on cold start by antivirus file scanning).
PyGithub and GitPython together pull in ~200 extra module files.

To keep startup fast, the heavy libraries are imported **lazily, inside the tool
functions that need them**, rather than at module top level:

- `server.py` imports `github_operations`, `git_operations`, and the
  branch-status checks inside the relevant `@mcp.tool()` bodies.
- `file_tools/file_operations.py` imports the git-move helpers inside `move_file`
  only, so the common read/write/edit/list/search path never loads GitPython.
- `reference_projects.py` imports `clone_repo` inside `ensure_available`.

**This is load-bearing, not incidental.** `tests/test_startup_performance.py`
asserts that importing `mcp_workspace.server` does **not** eagerly import
`github`/`git` and that a full process import stays under three seconds. Keep
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

## Architecture Enforcement Tools

We use four tools to enforce architectural boundaries:

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

### 3. pycycle

**Purpose:** Circular dependency detection

**Configuration:** None needed

**What it checks:**
- Import cycles between modules
- Circular dependencies at any level

**Run:**
```bash
# Windows
tools\pycycle_check.bat

# Linux/Mac
./tools/pycycle_check.sh
```

### 4. vulture

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

## Running All Checks

Run all quality and architecture checks at once:

```bash
# Windows
tools\run_all_checks.bat

# Linux/Mac
./tools/run_all_checks.sh
```

This runs:
1. Code formatting (black, isort)
2. Linting (pylint)
3. Type checking (mypy)
4. Tests (pytest)
5. Import contracts (import-linter)
6. Architecture boundaries (tach)
7. Circular dependencies (pycycle)

## CI/CD Integration

### Regular CI (All Branches)

Runs on every push:
- black
- isort
- pylint
- pytest
- mypy

### Architecture CI (PRs Only)

Runs only on pull requests:
- import-linter
- tach
- pycycle
- vulture

**Why PR-only?** Architecture checks are more expensive and are most valuable when reviewing code changes.

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
- [Pycycle on PyPI](https://pypi.org/project/pycycle/)
- [Vulture Documentation](https://github.com/jendrikseipp/vulture)
