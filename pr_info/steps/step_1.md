# Step 1 — `_chunk_paths` helper

Precondition: `src/mcp_workspace/git_operations/staging.py` exists and defines
`stage_specific_files` and `stage_all_changes` as described in `pr_info/steps/summary.md`.
If it does not, write one line to `pr_info/.blocked.txt` and stop.

## WHERE

- `src/mcp_workspace/git_operations/staging.py` — add a new private module-level function.
- `tests/git_operations/test_staging.py` — add a new test class/function for it.

## WHAT

```python
def _chunk_paths(paths: list[str], max_chars: int = 24000) -> list[list[str]]:
```

Private helper, not exported from `git_operations/__init__.py`. No repo access — pure
string-length logic, independently unit-testable.

## HOW

- No decorators, no new imports beyond stdlib typing already in the file.
- Not called anywhere yet in this step — step 2 wires it into `stage_specific_files`.
- Lives directly above or below `stage_specific_files` in `staging.py`.

## ALGORITHM

```
chunks = []; current = []; current_len = 0
for path in paths:
    added_len = len(path) + (1 if current else 0)   # +1 for the joining space
    if current and current_len + added_len > max_chars:
        chunks.append(current); current = []; current_len = 0
        added_len = len(path)
    current.append(path); current_len += added_len
if current: chunks.append(current)
return chunks
```

A single path longer than `max_chars` is never dropped — it becomes the sole entry of its
own chunk (the `current and ...` guard above only closes a chunk when it's non-empty, so an
oversized path still gets appended and emitted as a one-element chunk on the next
iteration or at the final flush).

## DATA

- Input: `list[str]` of git-relative paths (possibly empty).
- Output: `list[list[str]]`. Concatenating all chunks in order reproduces the input list
  exactly (order-preserving, nothing dropped, nothing duplicated).
- Empty input → `[]` (no chunks, not `[[]]`).

## TDD sequence (one commit)

1. Write `tests/git_operations/test_staging.py::test_chunk_paths` (or a small test class)
   as a `pytest.mark.parametrize`d test over these cases, run it, confirm it fails
   (`_chunk_paths` doesn't exist yet):
   - empty list → `[]`
   - a few short paths that fit comfortably under `max_chars` → one chunk, same order
   - paths engineered so the running total crosses `max_chars` partway through → two (or
     more) chunks, every path present exactly once, in order
   - one path longer than `max_chars` mixed with short paths → the long path is alone in
     its own chunk; short paths are not merged into it
2. Implement `_chunk_paths` in `staging.py` per the algorithm above.
3. Run the test, confirm it passes.
4. Run `mcp__mcp-tools-py__run_format_code`, then `run_pylint_check`, `run_pytest_check`
   (`extra_args: ["-n", "auto"]`), `run_mypy_check`, `run_ruff_check` on the touched files.
   All must pass.
5. Stage with `mcp__mcp-workspace__git` read-only checks as needed, then
   `git add`, `git commit` (Bash, per CLAUDE.md allowed commands) with a message describing
   the new helper. One commit for this step.

## LLM prompt for this step

```
Read pr_info/steps/summary.md and pr_info/steps/step_1.md in full before starting.

Implement step_1.md only: add the private helper `_chunk_paths` to
src/mcp_workspace/git_operations/staging.py, following the WHERE/WHAT/HOW/ALGORITHM/DATA
sections and the TDD sequence in step_1.md exactly. Do not touch `stage_specific_files`'s
behaviour yet — this step only adds the standalone helper and its tests.

Check the precondition at the top of step_1.md first; if it fails, write one line to
pr_info/.blocked.txt and stop.

Write the parametrized test first, confirm it fails, then implement the function, then
confirm it passes. Run run_format_code, run_pylint_check, run_pytest_check (-n auto),
run_mypy_check, run_ruff_check — all must pass. Produce exactly one commit containing the
test and the implementation together.
```
