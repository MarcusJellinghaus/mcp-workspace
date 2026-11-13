# Step 1 — Rules file parser (`access_rules.py`)

## LLM prompt

> Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_1.md`), and issue #83 (Rules file, Invalid rules file, Constraints: Matching engine).
> Implement step 1 only: first the probe, then the tests, then `src/mcp_workspace/file_tools/access_rules.py`.
> Do not wire the module into any tool yet. Run pylint, pytest (`-n auto`) and mypy; all must pass. Format, then make exactly one commit.

## Precondition — probe pathspec

Before writing code, run a scratch probe (`.scratch/test_probe.py`, see CLAUDE.md "Scratch probes") confirming on the installed pathspec:

- `PathSpec.from_lines("gitignore", ["config/", "config/local.json"]).check_file("config/local.json").index == 1`, and with the lines swapped the index is the `config/` line (last match wins both ways);
- `/logs/` matches `logs/` and `logs/a.log`; `/.scratch/` does **not** match `.scratch` (no slash);
- no match gives `index is None`; a comment-only line compiles to a pattern with `regex is None`.

If any assertion fails, write one line to `pr_info/.blocked.txt` naming the failing assertion and stop. Delete `.scratch/` afterwards.

## WHERE

- New: `src/mcp_workspace/file_tools/access_rules.py`
- New: `tests/file_tools/test_access_rules.py`

## WHAT

```python
ACCESS_RULES_FILE = ".mcp-file-access"
READ_ONLY = "read-only"
READ_WRITE = "read-write"

@dataclass(frozen=True)
class AccessRule:
    level: str      # READ_ONLY or READ_WRITE
    pattern: str    # as written in the file
    line: int       # 1-based

@dataclass(frozen=True)
class AccessRules:
    rules: tuple[AccessRule, ...] = ()
    problems: tuple[str, ...] = ()
    _spec: PathSpec | None = field(default=None, compare=False, repr=False)

    def match(self, rel_path: str, is_dir: bool = False) -> AccessRule | None: ...
    def leads_into(self, rel_dir: str) -> bool: ...

def load_access_rules(project_dir: Path) -> AccessRules: ...
def validate_access_rules(project_dir: Path) -> list[str]: ...
def access_rules_warning(problems: Sequence[str]) -> str | None: ...
```

## HOW

- Pure module: imports only `pathspec`, stdlib and `logging`. No import from other `file_tools` modules.
- `logger = logging.getLogger(__name__)`; module-level `_reported: set[str]` for "warn once per distinct problem".
- No caching of the parsed file (re-read on every call).

## ALGORITHM

```
load_access_rules(project_dir):
    f = project_dir / ACCESS_RULES_FILE
    missing -> AccessRules();  is_dir -> problem "is a directory";  OSError -> "cannot be read: <e>";  bad UTF-8 -> "is not valid UTF-8"
    for n, raw in lines: strip; skip blank / '#'; split(maxsplit=1) -> (level, pattern) else "line n: expected '<level> <pattern>'"
        level unknown -> "line n: unknown level '<level>'";  pattern starts '!' -> "line n: negation '!' is not allowed"
        pattern compiles to nothing / raises -> "line n: invalid pattern '<pattern>'"
    log each problem not yet in _reported (key: f"{project_dir}: {problem}"); if problems: return AccessRules(problems=...)  # no rules: fail safe
    return AccessRules(rules, _spec=PathSpec.from_lines("gitignore", [lower-on-win32(p) for p]))
```

```
match(rel_path, is_dir): if no spec -> None; p = rel_path + "/" if is_dir; lower on win32
    idx = spec.check_file(p).index; return rules[idx] if idx is not None else None
leads_into(rel_dir): for each rule whose pattern is anchored (a '/' other than a trailing one):
    prefix = leading segments (leading '/' stripped) before the first segment containing * ? [ or \
    True if prefix == rel_dir or prefix.startswith(rel_dir + "/")  (both lower-cased on win32)
```

## DATA

- `problems` strings: `"line 3: unknown level 'readonly'"`, `"is not valid UTF-8"`, … (no file name; callers prefix `.mcp-file-access is invalid: `).
- `validate_access_rules` → `list(load_access_rules(project_dir).problems)`; `[]` when the file is absent or valid.
- `access_rules_warning(problems)` → `None` when empty, else
  `"WARNING: .mcp-file-access is invalid (<'; '.join(problems)>) - writes are refused and no gitignored path is exposed."`

## Tests (`tests/file_tools/test_access_rules.py`, write first)

- Absent file → no rules, no problems.
- Both levels parse; `#` comments and blank lines skipped; extra whitespace between level and pattern allowed.
- Last match wins in both directions (`read-only config/` + `read-write config/local.json`, and swapped).
- `match(".scratch", is_dir=True)` matches `/.scratch/`; `match(".scratch/a/b.py")` matches; `match("other")` is `None`.
- Win32 only (`skipif`): `.MCP.json` matches `/.mcp.json`.
- Invalid: unknown level, missing pattern, `!` negation, comment-only pattern, non-UTF-8 bytes, directory at the path → problems contain the line number / reason, and `rules == ()`.
- Warning logged once: loading the same invalid file twice logs one WARNING (`caplog`).
- `leads_into`: `read-only /logs/sub/*.log` → `logs` and `logs/sub` True, `other` False; unanchored `*.log` → False everywhere; `**/x` → False.
- `access_rules_warning([])` is `None`; with problems contains every problem.
