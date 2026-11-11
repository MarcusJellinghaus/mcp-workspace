# Step 2 — `file_tools/line_endings.py`

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_2.md`: create
> `src/mcp_workspace/file_tools/line_endings.py` with the classifier, `describe_line_endings` and
> `target_newline`. Write the tests first. No callers yet. Run pylint, pytest (`-n auto`), mypy
> and lint-imports, all green. Run `run_format_code`, then make one commit.

## WHERE

- `src/mcp_workspace/file_tools/line_endings.py` — new
- `tests/file_tools/test_line_endings.py` — new

## WHAT

```python
PLATFORM_NEWLINE: str = os.linesep  # tests monkeypatch this

def count_line_endings(data: bytes) -> tuple[int, int, int]:
    """Return (crlf, lone lf, lone cr) counts."""

def describe_line_endings(text: str) -> str:
    """Line count and style for a non-empty text, e.g. "488 lines, CRLF" or "1 line"."""

def target_newline(existing: bytes | None, rel_path: str, project_dir: Path | None) -> str:
    """Line ending to write: existing file's style, else gitattributes eol=, else platform."""

def _eol_from_gitattributes(rel_path: str, project_dir: Path | None) -> str:
    """Map eol=lf / eol=crlf to "\n" / "\r\n"; anything else or any error -> PLATFORM_NEWLINE."""
```

## HOW

- `_eol_from_gitattributes` lazily imports `get_eol_attribute` from `mcp_workspace.git_operations`
  inside a `try`. Add a comment like the one in `_determine_move_method`: "Lazy import: keeps
  GitPython off the common file-operation import path".
- Use one `except Exception` with
  `# pylint: disable=broad-exception-caught  # git missing / not a repo / any git error -> platform default`
  and a `logger.debug` line.
- Read `PLATFORM_NEWLINE` at call time (module global), so monkeypatching works.

## ALGORITHM

```
count_line_endings: crlf = data.count(b"\r\n"); return crlf, data.count(b"\n")-crlf, data.count(b"\r")-crlf

describe_line_endings(text):
    data = text.encode("utf-8"); crlf, lf, cr = count_line_endings(data)
    lines = crlf + lf + cr + (1 if data and not data.endswith((b"\n", b"\r")) else 0)
    styles = [name for name, n in (("CRLF", crlf), ("LF", lf), ("CR", cr)) if n]
    style = styles[0] if len(styles) == 1 else ("mixed" if styles else None)
    return f"{lines} line{'s' if lines != 1 else ''}" + (f", {style}" if style else "")

target_newline(existing, rel_path, project_dir):
    if existing:  pairs = [(crlf,"\r\n"), (lf,"\n"), (cr,"\r")]; top = max counts
        if top: winners = [nl for n, nl in pairs if n == top]
                return winners[0] if len(winners) == 1 else PLATFORM_NEWLINE
    return _eol_from_gitattributes(rel_path, project_dir)   # new / empty / no line breaks

_eol_from_gitattributes: project_dir None -> PLATFORM_NEWLINE
    try: value = get_eol_attribute(rel_path, project_dir) except Exception: PLATFORM_NEWLINE
    return {"lf": "\n", "crlf": "\r\n"}.get(value or "", PLATFORM_NEWLINE)
```

## DATA

- `count_line_endings` → `(crlf, lf, cr)`.
- `describe_line_endings` → `str`. Callers handle the empty body separately (step 7).
- `target_newline` → one of `"\n"`, `"\r\n"`, `"\r"`.

## Tests (`tests/file_tools/test_line_endings.py`)

- **`count_line_endings`:**
  - `b"a\r\nb\nc\rd\r\n\r\r\n\n"` → `(3, 2, 2)`
  - `b"\r\r\n"` → `(1, 0, 1)`
  - `b""` → `(0, 0, 0)`
- **`describe_line_endings`:**
  - `"a\r\nb\r\n"` → `"2 lines, CRLF"`
  - `"a\nb"` → `"2 lines, LF"`
  - `"a\rb\r"` → `"2 lines, CR"`
  - `"a\r\nb\n"` → `"2 lines, mixed"`
  - `"abc"` → `"1 line"`
  - `"a\x0b\x0cb c"` → `"1 line"` (not `splitlines`)
  - non-ASCII text counts correctly
- **`target_newline` with `existing` bytes:**
  - each pure style is kept: CRLF, LF, CR
  - a mixed file returns the majority ending
  - a tie returns the monkeypatched `PLATFORM_NEWLINE`; run the tie test with it set to `"\n"`
    and again with `"\r\n"`
- **`eol=` branch.** Monkeypatch `mcp_workspace.git_operations.get_eol_attribute`. Cover
  `existing=None`, `b""` and `b"no breaks"`:
  - `"lf"` → `"\n"`
  - `"crlf"` → `"\r\n"`
  - `"unspecified"` / `None` / `"set"` → platform default
  - the patched function raises → platform default
  - `project_dir=None` → platform default, and the lookup is not called
- **Lookup not called** when `existing` has line breaks (patched function asserts it is not called).
- **Integration.** A `git.Repo.init(tmp_path)` repo with `.gitattributes` `*.sh eol=lf`, platform
  monkeypatched to `"\r\n"`:
  - `target_newline(None, "x.sh", tmp_path)` → `"\n"`
  - a `tmp_path` that is not a repo → platform default
