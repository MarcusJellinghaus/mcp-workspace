# Step 2 — Add `error_category` field to `CommitResult` (no behavior change)

> **LLM prompt** — Read `pr_info/steps/summary.md` for context, then implement
> exactly this step. Make one commit at the end. Run `pylint`, `mypy`, and
> `pytest` (use the fast-mode `-m "not ..."` exclusions for iteration; then a
> full run including `git_integration`).

## Why this step exists

Step 3 needs a typed slot on `CommitResult` where it can record *why* a commit
failed (signing vs commit vs validation). Splitting "add the field" from "use
the field" gives a small, mechanical, reviewable diff that mypy enforces is
complete. After this step, `error_category` is `None` everywhere — no
behavior change, no new logic — but the type system now requires every dict
literal returning `CommitResult` to include the key.

## WHERE

```
src/mcp_workspace/git_operations/core.py        # modify
src/mcp_workspace/git_operations/commits.py     # modify (4 dict literals)
src/mcp_workspace/git_operations/workflows.py   # modify (3 dict literals)
tests/git_operations/test_commits.py            # modify (one new assertion)
```

## WHAT

### `core.py`

Extend `CommitResult` with the new field:

```python
from typing import Literal, Optional, TypedDict

class CommitResult(TypedDict):
    """Result of a git commit operation."""

    success: bool
    commit_hash: Optional[str]
    error: Optional[str]
    error_category: Optional[Literal["signing_failed", "commit_failed", "validation_failed"]]
```

Keep `total=True` (the default) — this is the safety net that forces every
dict-literal return site to spell out the field.

### `commits.py`

Find all four `return {...}` literals in `commit_staged_files()` (the three
failure-path returns and the one success-path return) and add
`"error_category": None` to each. **No other changes** — no logic, no
docstring rewrites, no exception handling tweaks. Those land in step 3.

### `workflows.py`

Find all three `return {...}` literals in `commit_all_changes()`:
1. The not-a-repo path.
2. The no-changes early-return success path.
3. The `stage_all_changes` returned-False path.

Plus the broad `except Exception` path's return literal (a fourth, if present
— grep to confirm).

Add `"error_category": None` to each. The `commit_result` returned from the
delegated `commit_staged_files()` call already conforms to the new TypedDict
shape, so no change needed there.

### `test_commits.py`

Add one assertion to one existing happy-path test (e.g.,
`test_commit_staged_files`) confirming `result["error_category"] is None`.
This is the minimal TDD-flavoured verification that the field exists and
defaults to `None` on success. Do **not** sprinkle this assertion across
every existing test — the new mock tests in step 3 will cover the field
exhaustively.

## HOW

- `Literal` import: from `typing` (already imports from `typing` in
  `core.py`).
- No new public exports. `CommitResult` is already exported from
  `mcp_workspace.git_operations.__init__`; the schema change is additive.
- No fixture changes (those landed in step 1).

## ALGORITHM

```
update CommitResult TypedDict: add error_category field (Literal | None)
for each return-dict literal in commits.py and workflows.py:
    add "error_category": None
add one assertion in test_commits.py:
    result["error_category"] is None on the success path
```

## DATA

`CommitResult` dict shape after this step:

```python
{
    "success": bool,
    "commit_hash": Optional[str],
    "error": Optional[str],
    "error_category": None,    # always None until step 3
}
```

## Verification

- `mypy --strict` passes — this is the load-bearing check. Any missed dict
  literal will be flagged.
- `pylint` clean.
- `pytest` — all existing tests pass; the new single assertion passes.
- `pytest -m "git_integration"` passes.

## Commit message

```
refactor(git_operations): add error_category field to CommitResult

Mechanical addition of an Optional[Literal[...]] error_category field
to CommitResult, threaded as None through every existing return-dict
literal in commits.py and workflows.py. No behavior change; TypedDict
total=True ensures step 3 cannot forget a return site (refs #180).
```
