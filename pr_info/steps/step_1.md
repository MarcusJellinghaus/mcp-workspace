# Step 1 — `get_eol_attribute` in `git_operations`

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_1.md`: add
> `get_eol_attribute` to `git_operations/file_tracking.py` and export it. Write the tests first.
> Run pylint, pytest (`-n auto`) and mypy, all green. Run `run_format_code`, then make one commit.

## WHERE

- `src/mcp_workspace/git_operations/file_tracking.py` — new function
- `src/mcp_workspace/git_operations/__init__.py` — import and add to `__all__` (alphabetical)
- `tests/git_operations/test_init_exports.py` — expected count 70 → 71
- `tests/git_operations/test_eol_attribute.py` — new

## WHAT

```python
def get_eol_attribute(rel_path: str, project_dir: Path) -> str | None:
    """Return the gitattributes ``eol`` value for rel_path (works for missing paths).

    Raises:
        InvalidGitRepositoryError: project_dir is not a repository root.
        Exception: Whatever GitPython raises; callers fall back on any error.
    """
```

## HOW

- Uses `safe_repo_context` (already imported in `file_tracking.py`; it uses
  `search_parent_directories=False`) and `run_git_raw` from `.core`.
- No timeout and no `try/except`: the caller (step 2) owns the fallback.

## ALGORITHM

```
git_path = rel_path.replace("\\", "/")
with safe_repo_context(project_dir) as repo:
    rc, out, _ = run_git_raw(repo, "check_attr", "-z", "eol", "--", git_path)
if rc != 0: return None
fields = out.split(b"\0")            # b"path\0eol\0value\0"
return fields[2].decode("utf-8") if len(fields) > 2 else None
```

## DATA

`"lf"`, `"crlf"`, `"unspecified"`, `"unset"`, `"set"` or another value; `None` on a nonzero exit.

## Tests (`tests/git_operations/test_eol_attribute.py`, using the `git_repo` fixture)

- `.gitattributes` `*.sh eol=lf` → `"lf"` for `run.sh`, a path that does not exist yet.
- `*.bat eol=crlf` → `"crlf"`.
- A path with no rule → `"unspecified"`.
- A nested path `sub/dir/x.sh` → `"lf"`. Also pass it with backslashes and get the same result.
- A plain `tmp_path` folder (not a repo) → raises (`pytest.raises(Exception)`).
