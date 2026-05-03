# Refactoring Principles

Quick reference for refactoring rules and tools. For detailed process, examples, and checklists, see the [Safe Refactoring Guide](../../docs/processes-prompts/refactoring-guide.md).

## Key Rules

- **Move, don't change.** Logic changes belong in a separate PR.
- **Only adjust imports.** Use `move_symbol` — it updates imports automatically.
- **Clean deletion, no legacy artifacts.** No stubs, no re-exports for backward compatibility.
- **Small steps.** One module per PR. Keep diffs under 25,000 tokens.
- **Tests mirror source structure.**

## Process

1. Plan target structure
2. Move source code — `move_symbol` / `move_module`
3. Move tests to mirror new structure
4. Review diff — `mcp__mcp-workspace__git` with command `"diff"` (remaining diff should be imports only)
5. Run all checks — pytest, pylint, mypy, ruff
6. Check file sizes — `mcp__mcp-workspace__check_file_size`

See [Safe Refactoring Guide](../../docs/processes-prompts/refactoring-guide.md) for the full checklist.
