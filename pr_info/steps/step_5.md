# Step 5 — `ref_relative_path`: lexical paths at the ref

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement **only** `pr_info/steps/step_5.md`.
> Write the tests first, then the implementation. Use the MCP tools from `.claude/CLAUDE.md`.
> Run pylint, pytest (`extra_args: ["-n", "auto"]`) and mypy; all must pass. Run
> `run_format_code`, then make exactly one commit for this step.

## WHERE

- `src/mcp_workspace/file_tools/path_utils.py`
- `tests/file_tools/test_ref_relative_path.py` (new)

## WHAT

```python
def ref_relative_path(path: str, root: Path) -> str:
    """Turn a caller's path into a repo-relative, forward-slash path for a tree lookup.

    Lexical only: nothing is resolved against the local checkout (``normalize_path``
    would resolve symlinks and reject paths that are valid upstream).

    Returns:
        The relative path with forward slashes; "" for the root itself.

    Raises:
        ValueError: '..' segment, NUL byte, a .git entry under any spelling, or an
            absolute path outside ``root`` — with the same texts as ``normalize_path``.
    """
```

## HOW

Reuse `_outside_error` and `is_path_in_git_dir` from the same module; same messages as
`normalize_path`:
- `..` → `_outside_error(path, root, "contains '..' traversal and would escape")`
- NUL → `_outside_error(path, root, _UNRESOLVABLE)`
- absolute outside → `_outside_error(path, root, "resolves to a location")`
- `.git` → `"Security error: Path '{path}' is inside a git directory, which the file tools do not access."`

## ALGORITHM

```
if "\0" in path: raise NUL error
p = path.replace("\\", "/")
if PureWindowsPath(path).drive or p.startswith("/"):            # absolute (or drive-relative)
    base = str(root.resolve()).replace("\\", "/").rstrip("/") + "/"
    fold = str.casefold if os.name == "nt" else (lambda s: s)
    if not fold(p).startswith(fold(base)): raise outside error
    p = p[len(base):]
parts = [s for s in p.split("/") if s not in ("", ".")]
if ".." in parts: raise traversal error
rel = "/".join(parts);  if is_path_in_git_dir(rel): raise .git error
return rel
```

## DATA

`str` — e.g. `"src/x.py"`, `""` for `"."` / `"./"` / the root's absolute path.

## Tests (write first)

- `"src/x.py"`, `"src\\x.py"`, `"./src/x.py"`, `".\\src\\x.py"` → `"src/x.py"`.
- `str(root / "src" / "x.py")` → `"src/x.py"`; with an unresolved `root` (e.g. containing a
  `.` segment, or a symlinked parent where available) → still `"src/x.py"`.
- win32 only (`skipif`): different drive-letter case and mixed separators of the absolute
  path → `"src/x.py"`.
- `"."` → `""`.
- `"../x"`, `"src/../x"` → `ValueError` with "traversal".
- An absolute path outside `root` → `ValueError` with "outside the project directory".
- `".git/config"`, `".GIT/config"`, `".git./config"`, `"sub/.git/HEAD"` → `ValueError` with
  "inside a git directory"; `".github/x.yml"` → `".github/x.yml"`.
- `"a\0b"` → `ValueError`.
