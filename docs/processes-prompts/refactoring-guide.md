# Safe Refactoring Guide

Guidelines for refactoring code safely, whether splitting large files or restructuring architecture.

## Why This Matters

Large files (>750 lines) and poor code organization:

- Consume excessive LLM context
- Make navigation difficult
- Increase merge conflict risk
- Obscure architectural boundaries

## Core Principles

### 1. Move, Don't Change

**Critical rule**: Functions and classes should be moved, not modified.

```python
# GOOD: Function moved as-is
# old: src/utils/helpers.py
# new: src/utils/string_helpers.py

# BAD: Function modified during move
# Changing logic while relocating - do this in a separate PR
```

### 2. Only Adjust Imports

The only code changes should be:

- Import statements in the moved file
- Import statements in files that use the moved code
- Re-exports in `__init__.py` files (if maintaining API compatibility)

### 3. Clean Deletion, No Legacy Artifacts

When moving code to a new location:

- **Delete the old files entirely** - Do not leave empty modules or stubs
- **No deprecation warnings** - Update all consumers to use the new location directly
- **No re-exports for backward compatibility** - This creates hidden dependencies and technical debt
- **Update all imports immediately** - Every file that imported from the old location must be updated

Clean code is preferred over gradual migration. If external packages depend on the old location, coordinate the change or document it as a breaking change.

### 4. Small Steps

LLMs struggle with large moves. Break refactoring into:

- **One module per PR** when possible
- **Keep PR diffs under 25,000 tokens**
- **Move related functions together** (e.g., all string utilities)

## Process

### Step 1: Plan the Target Structure

Before moving anything:

1. Identify the "ideal" location for each component
2. Check that test files mirror source structure
3. Verify the new structure aligns with import linter / tach rules

### Step 2: Move Source Code (Using MCP Refactoring Tools)

Use the MCP refactoring tools — they move code and update all imports automatically:

1. `mcp__mcp-tools-py__list_symbols(file=...)` — inventory the source file
2. `mcp__mcp-tools-py__move_symbol(source_file=..., symbol_name=..., dest_file=..., dry_run=true)` — preview
3. `mcp__mcp-tools-py__move_symbol(source_file=..., symbol_name=..., dest_file=...)` — execute
4. Repeat for each symbol/group
5. Update `__init__.py` re-exports if needed
6. Update `.importlinter` layering contracts if the split introduces sub-layers (see [Import Linter](#import-linter) below)

### Step 3: Move Tests

Tests should mirror source structure:

```
src/mcp_coder/utils/string_helpers.py
tests/utils/test_string_helpers.py
```

### Step 4: Verify

After all moves, verify the refactoring:

#### Compact Diff

```bash
mcp-coder git-tool compact-diff
```

Suppresses moved-code blocks from the diff output. After a pure refactoring, the remaining diff should contain **only import changes and new/deleted file headers**. If you see logic changes in the compact diff, something was modified during the move.

#### File Size Check

```bash
mcp-coder check file-size --max-lines 750
```

Verifies all tracked Python files are under the line threshold. If split files were previously in `.large-files-allowlist`, remove those entries. Stale entries are reported automatically.

#### Import Linter

When splitting a module into sub-modules, the new files may have internal dependencies (e.g. `branch_queries` imports from `repository_status`). If the import linter uses a `layers` contract with `|` (pipe) separators, siblings can't import each other.

**Fix:** Use sub-layers — put the dependency on a lower layer than its consumers:
```ini
# Before (single module):
    mcp_coder.utils.git_operations.readers

# After (split into sub-layers):
    mcp_coder.utils.git_operations.branch_queries | mcp_coder.utils.git_operations.parent_branch_detection
    mcp_coder.utils.git_operations.repository_status
```

#### Standard Checks

```bash
# Import structure
./tools/lint_imports.sh
./tools/tach_check.sh

# Functionality (Claude Code MCP tools)
mcp__mcp-tools-py__run_pytest_check
mcp__mcp-tools-py__run_pylint_check
mcp__mcp-tools-py__run_mypy_check
```

## Common Patterns

### Splitting a Large File

1. Identify logical groupings (by responsibility, by domain)
2. Create new files for each group
3. Move functions one group at a time
4. Delete the original file — update all consumers to use new locations directly

### Architectural Restructuring

1. Update `.importlinter` and `tach.toml` with new module boundaries
2. Move code to match new structure
3. Fix any import violations
4. Update architecture documentation

## Checklist

Before merging a refactoring PR:

- [ ] No function/class logic was changed (only moved) — verify with `mcp-coder git-tool compact-diff`
- [ ] All imports updated correctly (automatic when using `move_symbol`)
- [ ] Tests moved to mirror source structure
- [ ] `lint-imports` passes
- [ ] `tach check` passes
- [ ] All unit tests pass
- [ ] `mcp-coder check file-size --max-lines 750` passes
- [ ] `.large-files-allowlist` updated (remove entries for split files)
- [ ] `.importlinter` updated if modules were split (sub-layers)
- [ ] PR diff is under 25,000 tokens

## Related

- [Refactoring Principles](../../.claude/knowledge_base/refactoring_principles.md) — quick-reference rules and tool tables (loaded by slash commands)
