# Step 4 — Export `verify_github_security` from the package

See [summary.md](./summary.md) for overall architecture and context.

## Goal

Make `verify_github_security` part of `mcp_workspace.github_operations`'s
public surface, so mcp_coder can import it (directly, or via its own
`src/mcp_coder/mcp_workspace_github.py` shim — that re-export happens in
mcp_coder#1180, not here). TDD: add the export assertion to the existing
package-exports test first, confirm it fails, then wire the export.

## WHERE

- Modify `src/mcp_workspace/github_operations/__init__.py`
- Modify `tests/github_operations/test_package_exports.py`

## WHAT

No new functions — this step only changes imports/`__all__` in
`__init__.py` and adds one assertion to an existing test file.

## HOW

- In `__init__.py`, add `from ._security_probes import verify_github_security`
  next to the existing `from .verification import CheckResult, verify_github`
  line.
- Add `"verify_github_security"` to `__all__`, keeping the list
  alphabetically sorted (matches the existing ordering in that file).
- In `test_package_exports.py`, add `verify_github_security` to the
  existing import from `mcp_workspace.github_operations` and a new test
  function following the file's existing style (see
  `test_issue_identity_mismatch_error_exported`), asserting it is
  importable and present in `github_operations.__all__`.

## ALGORITHM

Not applicable — this step is import/export wiring only, no new logic.

## DATA

Not applicable.

## Tests to add (`test_package_exports.py`)

```python
def test_verify_github_security_exported() -> None:
    """verify_github_security is importable and in __all__."""
    assert verify_github_security is not None
    assert "verify_github_security" in github_operations.__all__
```

## Precondition check

None — Steps 1-3 already provide the function this step exports. Proceed
directly to implementation.

## Commit

One commit. Suggested message:
`feat(github_operations): export verify_github_security`

## LLM prompt for this step

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_4.md` in this
> repo. Steps 1-3 are already implemented and committed. Implement exactly
> what Step 4 describes: add the new test to
> `tests/github_operations/test_package_exports.py` first, confirm it
> fails, then update `src/mcp_workspace/github_operations/__init__.py` to
> import and export `verify_github_security` per Step 4's HOW section. Run
> `mcp__mcp-tools-py__run_pylint_check`,
> `mcp__mcp-tools-py__run_pytest_check` (with `extra_args: ["-n", "auto"]`),
> `mcp__mcp-tools-py__run_mypy_check`, and
> `mcp__mcp-tools-py__run_lint_imports_check` (new export touches the
> package boundary the `.importlinter` config governs); fix anything they
> flag. Run `mcp__mcp-tools-py__run_format_code`, then make exactly one
> commit. This is the final step — once it passes, the full feature for
> issue #314 is complete.
