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
_segments(s) = [x for x in s.replace("\\", "/").split("/") if x not in ("", ".")]

if "\0" in path: raise NUL error
parts = _segments(path)
if ".." in parts: raise traversal error
if PureWindowsPath(path).drive or path.replace("\\", "/").startswith("/"):   # absolute
    fold = str.casefold if os.name == "nt" else (lambda s: s)
    roots = [_segments(str(root.resolve())), _segments(str(root))]   # resolved, then lexical
    prefix = next((r for r in roots
                   if [fold(x) for x in parts[:len(r)]] == [fold(x) for x in r]), None)
    if prefix is None: raise outside error
    parts = parts[len(prefix):]
rel = "/".join(parts);  if is_path_in_git_dir(rel): raise .git error
return rel
```

Segment-wise comparison, with `""`/`"."` segments dropped on both sides. An absolute path
built from the unresolved root (a `.` segment, a symlinked parent such as macOS `tmp_path`)
matches the lexical root, and one built from the resolved root matches the resolved root.
`..` is rejected before the prefix check, so it can never be stripped away.

## DATA

`str` — e.g. `"src/x.py"`, `""` for `"."` / `"./"` / the root's absolute path.

## Tests (write first)

- `"src/x.py"`, `"src\\x.py"`, `"./src/x.py"`, `".\\src\\x.py"` → `"src/x.py"`.
- `str(root / "src" / "x.py")` → `"src/x.py"`.
- Unresolved root, parametrised: `root = tmp / "a" / "." / "ref"` and (`skipif` symlinks are
  unavailable) `root = <symlink to a dir>/ref` — the input built from that unresolved root
  (`str(root / "src" / "x.py")`) and the input built from `root.resolve()` both give
  `"src/x.py"`. On macOS, plain `tmp_path` (under the `/var` → `/private/var` symlink)
  covers the symlinked-parent case.
- win32 only (`skipif`): different drive-letter case and mixed separators of the absolute
  path → `"src/x.py"`.
- `"."` → `""`.
- `"../x"`, `"src/../x"` → `ValueError` with "traversal".
- An absolute path outside `root` → `ValueError` with "outside the project directory".
- `".git/config"`, `".GIT/config"`, `".git./config"`, `"sub/.git/HEAD"` → `ValueError` with
  "inside a git directory"; `".github/x.yml"` → `".github/x.yml"`.
- `"a\0b"` → `ValueError`.
