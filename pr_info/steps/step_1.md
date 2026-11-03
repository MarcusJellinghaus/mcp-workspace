# Step 1 — Move `_chunk_paths` to `core.py`

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_1.md` exactly.
> This step is a pure refactor with no behaviour change. Run format, pylint, pytest
> (`-n auto`), mypy and lint-imports. All must pass. Then make one commit.

## WHERE

- `src/mcp_workspace/git_operations/core.py`
- `src/mcp_workspace/git_operations/staging.py`
- `tests/git_operations/test_staging.py`

## WHAT

`_chunk_paths(paths: list[str], max_chars: int = 24000) -> list[list[str]]`. Move it with its
body and docstring unchanged.

## HOW

- `core.py`: paste `_chunk_paths` directly after `to_git_paths`.
- `staging.py`: delete the function and add `_chunk_paths` to the existing
  `from .core import (...)` list, keeping the list alphabetical (`_chunk_paths` first).
- `tests/git_operations/test_staging.py`: remove `_chunk_paths` from the `staging` import and add
  `from mcp_workspace.git_operations.core import _chunk_paths`. mypy strict rejects importing a
  name that a module re-imports.
- Do **not** change the patch target `mcp_workspace.git_operations.staging._chunk_paths` in
  `tests/git_operations/test_unstage_paths.py`. `staging` still holds its own reference.

## TDD

Existing tests cover this step: `TestChunkPaths` in `test_staging.py` and the chunking test in
`test_unstage_paths.py`. Change the test import first (it fails), then move the function (it passes).

## ALGORITHM

None (code move).

## DATA

Unchanged.

## Commit

`refactor(git_operations): move _chunk_paths to core`
