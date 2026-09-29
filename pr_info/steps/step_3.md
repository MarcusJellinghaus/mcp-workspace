# Step 3 — `delete_directory` children and `_check_not_gitignored`

The two remaining emitting sites that step 1 does not reach. Both are one-line changes; the
bulk of this step is the coverage the issue calls for.

## WHERE

| File | Role |
|---|---|
| `src/mcp_workspace/file_tools/file_operations.py` | `delete_directory`, line 458 |
| `src/mcp_workspace/server.py` | `_check_not_gitignored`, line 280 |
| `tests/file_tools/test_delete_directory.py` | nested-child and message coverage |
| `tests/test_server.py` | `_check_not_gitignored` absolute-path coverage |
| `tests/file_tools/test_move_operations.py` | nested-path coverage for `move_file`'s dict |
| `tests/file_tools/test_search.py` | nested-path coverage for `skipped_files` |

## WHAT

```python
# file_operations.py:458 — delete_directory
all_rel = [rel_path] + [p.relative_to(project_dir).as_posix() for p in children]
#                                                  ^^^^^^^^^^  was: str(p.relative_to(project_dir))

# server.py:280 — _check_not_gitignored
file_path = path.relative_to(_project_dir).as_posix()
#                                          ^^^^^^^^^  was: str(path.relative_to(_project_dir))
```

No signature changes. No new imports.

## HOW

- `delete_directory`'s children are **not** routed through `normalize_path`. They are
  already known to be inside the project — `rglob` produced them under a validated
  `abs_path` — and re-validating each one would be redundant work on a list capped at 20
  displayed entries but unbounded in length.
- `rel_path` itself already carries the fix from step 1 via `normalize_path`, which is why
  the two `ValueError` messages (`:443` is-a-file, `:451` not-empty) and the idempotent
  "does not exist" return string (`:439`) need no edit — they interpolate `rel_path`.
- `_check_not_gitignored` reassigns `file_path` and then interpolates it into the raised
  `ValueError`, so the one change fixes both the gitignore lookup and the message.
- `move_file` has **no production work in this step**. Its returned dict carries `src_rel`
  and `dest_rel` from `_validate_move_parameters`, both already fixed by step 1's
  `normalize_path` change. Only its test is new.

## ALGORITHM

Which `delete_directory` outputs are fixed where:

```
rel_path            <- normalize_path      (step 1)  -> messages + first list entry
children entries    <- relative_to+as_posix (here)   -> the rest of the list
_format_deleted_paths caps at 20 + summary  (unchanged)
```

## DATA

- `delete_directory` → `list[str]`. Entry 0 is the directory itself; entries 1..n are its
  children, all forward-slash separated, all project-relative. The 20-entry cap and the
  `"... and N more (X files, Y dirs deleted total)"` summary line are unchanged.
- `_check_not_gitignored` → `None`, or raises `ValueError` whose message now carries a
  forward-slash project-relative path.
- `move_file` (util) → `Dict[str, Any]` with `source` and `destination` keys, both now
  forward-slash separated.

## Tests (write first)

1. `delete_directory` returns every entry forward-slash separated — the directory itself
   **and** a **nested** child (`<dir>/sub/nested.txt`), not only root-level entries.
2. `delete_directory`'s two `ValueError` messages (is-a-file, non-empty-without-recursive)
   and the idempotent "does not exist" return string each carry a forward-slash path. Use a
   nested directory so the assertion has a separator to be wrong about.
3. `_check_not_gitignored` emits a forward-slash path when the caller supplied an
   **absolute** path to a gitignored nested file.
4. `move_file`'s returned dict: `source` and `destination` are forward-slash separated for a
   nested source and a nested destination. There is no nested-path coverage today.
5. `search_files`' `skipped_files` entries are forward-slash separated for a nested
   unreadable file. There is no nested-path coverage today.

Existing `test_delete_directory.py` `pytest.raises(match=...)` patterns sit *after* the
embedded path, so they are unaffected. A sweep of `tests/` for assertions matching message
text containing a path found none.

## Checks

`run_format_code`, then `run_pylint_check`, `run_pytest_check` with `["-n", "auto"]`,
`run_mypy_check`. One commit.

---

## LLM prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_3.md`, then implement step 3.
> Step 1 must already be committed.
>
> Two one-line source changes: `delete_directory`'s children list at
> `src/mcp_workspace/file_tools/file_operations.py:458` and `_check_not_gitignored` at
> `src/mcp_workspace/server.py:280`, both switching `str(...relative_to(...))` to
> `....relative_to(...).as_posix()`.
>
> Everything else in this step is test coverage. Work test-first and write all five tests
> listed under **Tests** before editing `src/`. Two of them — `move_file`'s returned dict
> and `search_files`' `skipped_files` — need no source change at all; they cover paths
> already fixed by step 1 and have no nested-path coverage today.
>
> Do not route `delete_directory`'s children through `normalize_path`; they are already
> known to be inside the project. Do not edit `delete_directory`'s two `ValueError` messages
> or its "does not exist" string — they interpolate `rel_path`, which step 1 already fixed.
>
> Use the MCP tools per `CLAUDE.md`. Run `run_format_code`, then `run_pylint_check`,
> `run_pytest_check` with `extra_args: ["-n", "auto"]`, and `run_mypy_check`. All must pass.
> Commit once.
