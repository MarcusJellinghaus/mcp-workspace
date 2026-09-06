# Step 4 — Reference-project traversal coverage

Read [summary.md](./summary.md) first. Depends on step 1. Test-only commit.

`read_reference_file`, `list_reference_directory` and `search_reference_files` pass the
reference project's path in as `project_dir` and call the same utilities, so they inherited
the defect and inherit the fix with no extra code. That is precisely the problem: nothing in
`server_reference_tools.py` signals that it goes through the same chokepoint, and a
reference-project escape can reach the workspace or another reference project. One test says
it out loud.

Per the issue's Decisions table this is **one** `read_reference_file` test, not full parallel
coverage of all three tools.

## WHERE

`tests/test_reference_projects_mcp_tools.py` — one async test added to the existing
`read_reference_file` test class. No source file is touched.

## WHAT

```python
@pytest.mark.asyncio
async def test_read_reference_file_rejects_absolute_traversal(tmp_path: Path) -> None: ...
```

## HOW

- Use a **real** directory from `tmp_path` as the reference path, and do **not** mock
  `read_file_util` — the whole point is to let the real security check run. This differs from
  the neighbouring tests, which mock it because they are testing parameter forwarding.
- No `ensure_available` patch is needed either: it returns immediately when
  `project.path.exists()` (`reference_projects.py`), and here the directory exists. The
  neighbouring tests patch it only because their paths are fictional.
- Set `server_module._reference_projects` directly, the way every test in this module does.
- Resolve the reference path when constructing `ReferenceProject`, mirroring production —
  `main.py:142` binds an already-resolved path.

## ALGORITHM

```
ref = tmp_path/"ref"; ref.mkdir()
outside = tmp_path/"outside"; outside.mkdir(); (outside/"credentials.env").write_text("SECRET=1")
server_module._reference_projects = {"ref": ReferenceProject(name="ref", path=ref.resolve())}
escape = str(ref.resolve()/".."/"outside"/"credentials.env")
with pytest.raises(ValueError, match="Security error"):
    await read_reference_file("ref", escape)
```

## DATA

No new data structures. The assertion is the raised `ValueError` and its `"Security error"`
prefix; the secret file's content must never be returned.

## Checks

`run_format_code`, then `run_pylint_check`, `run_pytest_check` (`extra_args: ["-n", "auto"]`),
`run_mypy_check`.

After this step the whole acceptance list is covered. Confirm the run is green end to end and
note which symlink tests skipped locally — variant 2 (the symlink escape) is proven only by
the `ubuntu-latest` CI job, so state that plainly in the PR rather than reporting a local
green as full verification.

## Commit

`test(reference): cover absolute-path traversal (#290)`

## LLM prompt

> Implement step 4 of the plan in `pr_info/steps/step_4.md`, using `pr_info/steps/summary.md`
> for context. Steps 1–3 must already be committed.
>
> This is a test-only commit: add one async test to `tests/test_reference_projects_mcp_tools.py`
> proving `read_reference_file` rejects an absolute path that escapes the reference project
> directory. Use a real `tmp_path` directory as the reference path and do not mock
> `read_file_util` or `ensure_available` — the real security check has to run. Follow the
> module's existing convention of assigning `server_module._reference_projects` directly.
>
> Then run `run_format_code`, `run_pylint_check`, `run_pytest_check` with
> `extra_args: ["-n", "auto"]`, and `run_mypy_check`. One commit for the step.
>
> Finally, report which symlink-dependent tests skipped on this machine and state explicitly
> that variant 2 of the vulnerability is verified only by the Ubuntu CI job.
