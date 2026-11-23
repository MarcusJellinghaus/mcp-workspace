# Step 8 — Clone state moves into `WorkspaceContext`; `ensure_available` reports a clone

No behaviour change for the tools.

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement **only** `pr_info/steps/step_8.md`.
> Write the tests first, then the implementation. Use the MCP tools from `.claude/CLAUDE.md`.
> Run pylint, pytest (`extra_args: ["-n", "auto"]`), mypy and vulture; all must pass.
> Run `run_format_code`, then make exactly one commit for this step.

## WHERE

- `src/mcp_workspace/reference_projects.py`
- `src/mcp_workspace/toolset/_context.py`
- `src/mcp_workspace/toolset/reference.py` (`reference_project_path` only)
- `vulture_whitelist.py`
- `tests/test_reference_projects_utils.py`, `tests/test_reference_projects_mcp_tools.py`,
  `tests/test_reference_search_mcp_tools.py` (call-signature assertions only)

## WHAT

```python
# reference_projects.py — module globals _project_locks / _clone_failure_cache and
# clear_clone_failure_cache() are removed.
async def ensure_available(
    project: ReferenceProject,
    *,
    locks: dict[str, asyncio.Lock],
    failures: dict[str, str],
) -> Literal[True] | None:
    """... Returns: True if this call cloned the project, otherwise None."""

# toolset/_context.py
@dataclass
class ReferenceState:
    """Mutable per-context reference state (the context itself is frozen)."""
    clone_locks: dict[str, asyncio.Lock] = field(default_factory=dict)
    clone_failures: dict[str, str] = field(default_factory=dict)

@dataclass(frozen=True)
class WorkspaceContext:
    ...existing six fields, file_locks, git_write_lock...
    reference_state: ReferenceState = field(default_factory=ReferenceState)
```

## HOW

- `ensure_available` body is unchanged except: `lock = locks.setdefault(project.name, asyncio.Lock())`,
  `failures` replaces `_clone_failure_cache`, and `return True` after a successful clone.
  `None` keeps meaning "no clone", so existing `AsyncMock(return_value=None)` stubs stay valid.
- `reference_project_path(ctx, name)` passes `locks=ctx.reference_state.clone_locks,
  failures=ctx.reference_state.clone_failures` and still returns `project.path` (the clone
  signal is used in step 10).
- New `WorkspaceContext` field is defaulted and placed last, so the positional six-argument
  constructions in tests keep working. Update the class docstring's Attributes.
- `vulture_whitelist.py`: remove `_.clear_clone_failure_cache`.

## Tests (write first)

- `tests/test_reference_projects_utils.py::TestEnsureAvailable`: replace
  `clear_clone_failure_cache()` with fresh `locks={}`, `failures={}` per test; the
  "cache cleared" test passes a new `failures` dict instead; add: existing dir → returns
  `None`; successful (mocked) clone → returns `True`; failure is cached in the passed
  `failures` dict, not globally (a second dict allows a retry).
- Two `tool_specs()` tool sets do not share clone failures (a failure in one does not block
  the other).
- Update `assert_awaited_once_with(proj)` in `tests/test_reference_projects_mcp_tools.py`
  and `tests/test_reference_search_mcp_tools.py` to
  `assert_awaited_once_with(proj, locks=ANY, failures=ANY)`.
