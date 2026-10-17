# Step 1 — `MalformedBaseBranchError` in `issues/base.py`

See `pr_info/steps/summary.md` for full context. This step only touches the
exception type; nothing calls it from `server.py` yet.

## Precondition

`src/mcp_workspace/github_operations/issues/base.py` must contain `parse_base_branch`
raising a bare `ValueError` on a multi-line section (the current, unmodified
behavior), and `tests/github_operations/issues/test_base.py` must contain
`test_parse_base_branch_multiline_raises`. If either is missing or already
different, write one line to `pr_info/.blocked.txt` and stop.

## WHERE

- `src/mcp_workspace/github_operations/issues/base.py` (modify)
- `src/mcp_workspace/github_operations/issues/__init__.py` (modify)
- `tests/github_operations/issues/test_base.py` (modify)

## WHAT

New class in `base.py`:

```python
class MalformedBaseBranchError(ValueError):
    def __init__(self, content: str) -> None: ...
```

- Subclasses `ValueError` (so `except ValueError` elsewhere, in particular
  `IssueManager`, is unaffected).
- Stores the raw section text on `self.content` for the caller to inspect
  (e.g. to get the first line). Keep the existing message text, built from
  `content`, as the exception's `str()`.

`parse_base_branch` keeps its existing signature and docstring; only the
multi-line branch changes:

```python
if "\n" in content:
    raise MalformedBaseBranchError(content)
```

## HOW

- `base.py`: add `"MalformedBaseBranchError"` to `__all__` (alongside the
  existing four names).
- `issues/__init__.py`: change `from .base import parse_base_branch` to
  `from .base import MalformedBaseBranchError, parse_base_branch`; add
  `"MalformedBaseBranchError"` to `__all__`, next to the existing
  `"parse_base_branch"` entry.
- No change to `manager.py` — it already does `except ValueError`, which still
  matches.

## ALGORITHM

```
parse_base_branch(body):
    ... unchanged regex match, extract `content` ...
    if content is empty: return None
    if "\n" in content:
        raise MalformedBaseBranchError(content)   # was: raise ValueError(...)
    return content
```

## DATA

- `MalformedBaseBranchError.content: str` — the matched section's stripped
  text, newlines included (not yet split into lines; that happens in step 3).
- No other return values change. `parse_base_branch`'s three outcomes (value /
  `None` / raises) are unchanged; only the raised type is more specific.

## TDD order

1. In `tests/github_operations/issues/test_base.py`, add (keep the existing
   `test_parse_base_branch_multiline_raises` passing unchanged, since
   `MalformedBaseBranchError` is a `ValueError`):
   - `test_parse_base_branch_multiline_raises_malformed_base_branch_error`:
     call with a two-line section, assert
     `pytest.raises(MalformedBaseBranchError)`.
   - `test_malformed_base_branch_error_is_a_value_error`: assert
     `issubclass(MalformedBaseBranchError, ValueError)`.
   - `test_malformed_base_branch_error_carries_content`: raise it directly or
     via `parse_base_branch`, assert `exc.value.content == "line1\nline2"` for
     input `"### Base Branch\n\nline1\nline2\n"`.
   - Import `MalformedBaseBranchError` from
     `mcp_workspace.github_operations.issues.base` alongside the existing
     `parse_base_branch` import.
2. Run the new tests — they fail (class does not exist yet).
3. Implement the class and the `parse_base_branch` change in `base.py`.
4. Add the re-export in `issues/__init__.py`.
5. Run `mcp__mcp-tools-py__run_pytest_check` scoped to
   `tests/github_operations/issues/test_base.py` and to
   `tests/github_operations/issues/test_manager.py` (must stay green,
   unmodified) — both pass.

## Checks and commit

Run `mcp__mcp-tools-py__run_format_code`, then
`mcp__mcp-tools-py__run_pylint_check`, `mcp__mcp-tools-py__run_pytest_check`
(`extra_args: ["-n", "auto"]`), `mcp__mcp-tools-py__run_mypy_check`. All must
pass. Then `git add` + `git commit` (one commit) with a message such as:

```
feat(issues/base): add MalformedBaseBranchError

parse_base_branch now raises this ValueError subclass instead of a bare
ValueError on a multi-line Base Branch section, carrying the section's
content so callers can report its first line. IssueManager's existing
`except ValueError` is unaffected.
```

## LLM prompt for this step

```
Read pr_info/steps/summary.md for context, then implement
pr_info/steps/step_1.md exactly as written. Follow TDD: write the failing
tests in tests/github_operations/issues/test_base.py first, confirm they
fail, then add MalformedBaseBranchError to
src/mcp_workspace/github_operations/issues/base.py and re-export it from
src/mcp_workspace/github_operations/issues/__init__.py. Do not touch
server.py, main.py, or manager.py in this step. Run format, pylint, pytest
(-n auto), and mypy; all must pass, including the untouched
tests/github_operations/issues/test_manager.py. If the precondition in
step_1.md does not hold, write one line to pr_info/.blocked.txt and stop.
Make exactly one commit.
```
