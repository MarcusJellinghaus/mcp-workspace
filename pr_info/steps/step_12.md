# Step 12 — Acceptance tests for the exported toolset

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_12.md`.
> Add the issue's acceptance tests for the factory to `tests/toolset/test_toolset.py`. Consolidate the
> per-group spec tests from steps 3–11 into one table-driven test. No production change is expected.
> If a test exposes a production bug, fix it minimally in this step. Run all checks, format, commit.

## WHERE

- `tests/toolset/test_toolset.py`
- Production code only if a test fails because of a real defect.

## WHAT

```python
EXPECTED: dict[str, tuple[str, bool]] = {
    "read_file": ("workspace.read", True), ...,           # all 31 rows from the summary table
}

def test_groups_and_read_only_match_table(tmp_path: Path) -> None: ...
def test_read_and_write_tools_work_on_temp_project(tmp_path: Path) -> None: ...
@pytest.mark.parametrize("tool, kwargs", [...])
def test_read_write_tools_refuse_outside_paths(tmp_path: Path, tool: str, kwargs: dict[str, Any]) -> None: ...
@pytest.mark.parametrize("tool, kwargs", [...])
def test_read_write_tools_refuse_gitignored_paths(tmp_path: Path, tool: str, kwargs: dict[str, Any]) -> None: ...
def test_two_factories_do_not_interfere(tmp_path: Path) -> None: ...
def test_two_factories_have_separate_file_locks(tmp_path: Path) -> None: ...
def test_read_file_default_truncates_at_default_read_max_lines(tmp_path: Path) -> None: ...
@pytest.mark.asyncio
async def test_read_reference_file_default_truncates(tmp_path: Path) -> None: ...
def test_args_model_with_required_args_only(tmp_path: Path) -> None: ...
def test_args_model_rejects_invalid_arguments(tmp_path: Path) -> None: ...
```

## HOW

- **Table:**
  - `{s.name: (s.group, s.read_only) for s in tool_specs(tmp_path)} == EXPECTED`.
  - This replaces the per-group spec tests added in steps 3–11.
  - Keep the `iscoroutinefunction` assertions from those steps for the async tools
    (`edit_file`, `git`, `check_branch_status`, `read_reference_file`, `list_reference_directory`,
    `search_reference_files`). `get_reference_projects` is sync.
- **Read/write on a temp project:**
  - Run `save_file`, `append_file`, `await edit_file`, then `read_file`, `list_directory` and
    `search_files` via `spec.fn`.
  - Check the file content on disk and in the read results.
- **Outside paths:** `read_file("../outside.txt")`, `save_file("../x.txt", ...)`, `append_file`
  and `edit_file` on a path outside the project each raise `ValueError` (or the
  exception today's tests expect). Nothing is written outside.
- **Gitignored paths:**
  - Set up the project the same way `tests/test_file_tool_path_rules.py` does (a `.gitignore`
    with `secret.txt`, and `git init` if that file does).
  - `read_file` / `save_file` / `append_file` / `edit_file` on `secret.txt` raise.
  - `search_files` does not return its content.
- **Two factories:**
  - `a = make(tmp_path / "a", read_max_lines=2)`, `b = make(tmp_path / "b")`.
  - `a["save_file"]("f.txt", ...)` writes only under `a`.
  - `a["read_file"]` truncates at 2 lines while `b["read_file"]` on a 5-line file doesn't.
- **Separate file locks:**
  - Spy on `mcp_workspace.toolset.WorkspaceContext`: patch with `side_effect` that builds the real
    dataclass and appends it to a list.
  - Build two factories and run `edit_file` on the same relative path in each.
  - Assert the two contexts' `file_locks` dicts are distinct objects, and that each holds only its
    own project's absolute path.
- **Default truncation:**
  - Do not pass `read_max_lines`. Write a file with `DEFAULT_READ_MAX_LINES + 5` lines.
  - The result does not contain line `DEFAULT_READ_MAX_LINES + 1` and does contain the next-range note.
  - For `read_reference_file`, use `reference_projects={"ref": ReferenceProject(name="ref", path=ref_dir)}`
    and patch `mcp_workspace.toolset.reference.ensure_available` with `AsyncMock`.
- **`args_model`** (LangChain calling convention):
  - `m = spec.args_model.model_validate({"file_path": "f.txt"})`, then
    `spec.fn(**m.model_dump(exclude_unset=True))` returns the content.
  - Also `search_files` with `{"glob": "*.txt"}`.
  - Invalid input raises `pydantic.ValidationError`: a missing `file_path`, and
    `{"file_path": "f.txt", "start_line": "abc"}`.

## ALGORITHM

```
specs = {s.name: s for s in tool_specs(root, **settings)}
call sync:  specs[name].fn(**kwargs)
call async: await specs[name].fn(**kwargs)
assert observable effect (file on disk / returned text / raised error)
```

## DATA

None new.

## Checks

All checks pass. One commit: `test(toolset): acceptance tests for exported tool specs`.
