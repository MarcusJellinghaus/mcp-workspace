# Step 1 — Case-insensitive pattern classes; access-rules fix

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement this step
> (`pr_info/steps/step_1.md`). TDD: write the tests first, see them fail,
> then implement. Run `run_format_code`, pylint, pytest
> (`extra_args=["-n", "auto"]`), mypy and ruff; all must pass. Then make
> exactly one commit. Do not touch `search.py` (that is step 2).

## WHERE

- `src/mcp_workspace/file_tools/access_rules.py`
- `tests/file_tools/test_access_rules.py`
- `docs/ARCHITECTURE.md` (the `access_rules.py` bullet, lines ~171–173)

## WHAT

New in `access_rules.py`:

```python
class _CaseInsensitiveOnWin32(RegexPattern):
    """Prefix the generated regex with ``(?i)`` on win32."""

    @classmethod
    def pattern_to_regex(cls, pattern: AnyStr) -> tuple[AnyStr | None, bool | None]: ...


class AccessRulePattern(_CaseInsensitiveOnWin32, GitIgnoreBasicPattern):
    """Gitignore pattern for access rules, case-insensitive on win32."""


class GlobPattern(_CaseInsensitiveOnWin32, GitIgnoreSpecPattern):
    """Gitignore-spec pattern for search globs, case-insensitive on win32."""
```

(`GlobPattern` is added here because it shares the mixin; it is used in step 2.
vulture may flag it as unused until then. If it does, keep it anyway: it is
covered by the bytes / class test below, which references it.)

Changed:

- `_compiles(pattern: str) -> bool`: builds with `AccessRulePattern` and
  catches `(ValueError, re.error)`.
- `load_access_rules`: `PathSpec.from_lines(AccessRulePattern, [r.pattern for r in rules])`.
  No `_fold`, no try/except.
- `AccessRules.match`: `self._spec.check_file(path)`, no `_fold`.
- `_fold` docstring: it now only serves the literal-prefix comparison in
  `leads_into` (Args: "Directory or literal prefix to fold").

## HOW

Imports in `access_rules.py`:

```python
import re
from typing import AnyStr

from pathspec import PathSpec, Pattern, RegexPattern
from pathspec.patterns.gitignore.basic import GitIgnoreBasicPattern
from pathspec.patterns.gitignore.spec import GitIgnoreSpecPattern
```

Keep `import sys`: the mixin and `_fold` use it. Zero-argument `super()`,
no `# noqa`, no vulture whitelist entry.

## ALGORITHM

```
pattern_to_regex(cls, pattern):
    regex, include = super().pattern_to_regex(pattern)
    if sys.platform == "win32" and regex is not None:
        regex = "(?i)" + regex if isinstance(regex, str) else b"(?i)" + regex
    return regex, include
```

If strict mypy rejects the conditional expression under `AnyStr`, use an
`if isinstance(regex, str): … else: …` block with the same meaning.
Run mypy locally (win32 checks the win32 branch). If `run_mypy_check`
accepts extra args, also run it with `--platform linux` (what CI sees, with
`warn_unreachable = true`). If both cannot be made to pass, write one line
to `pr_info/.blocked.txt` and stop.

## DATA

- `pattern_to_regex` returns `(regex | None, include | None)`, same shape as
  pathspec. On win32 a non-`None` regex starts with `(?i)` / `b"(?i)"`.
- `AccessRules._spec` stays `PathSpec[Pattern] | None`.

## Tests (write first) — `tests/file_tools/test_access_rules.py`

1. Fixture:
   ```python
   @pytest.fixture
   def win32(monkeypatch: pytest.MonkeyPatch) -> None:
       """Make spec builds take the win32 (case-insensitive) branch."""
       monkeypatch.setattr(sys, "platform", "win32")
   ```
   It must be applied before `_load(...)`, which builds the spec. Patching
   only around `.match()` would test POSIX behaviour.
2. `test_invalid_line_gives_problem_and_no_rules`: add the case
   `("read-only /[b-a]x\n", "line 1: invalid pattern '/[b-a]x'")`.
3. `test_reversed_range_is_invalid_on_win32` (`@pytest.mark.usefixtures("win32")`):
   `_load(tmp_path, "read-only /[b-a]x\n").problems == ("line 1: invalid pattern '/[b-a]x'",)`.
4. Replace the skip-gated `test_match_is_case_insensitive_on_win32` with a
   parametrized `@pytest.mark.usefixtures("win32")` test:
   ```python
   @pytest.mark.parametrize(
       ("pattern", "path"),
       [
           ("/.mcp.json", ".MCP.json"),
           ("/[Z-a]x", "zx"),
           ("/[Z-a]x", "_x"),
           ("/[A-z]x", "_x"),
       ],
   )
   def test_match_is_case_insensitive_on_win32(tmp_path, pattern, path):
       rules = _load(tmp_path, f"read-only {pattern}\n")
       assert rules.problems == ()
       assert rules.match(path) is not None
   ```
5. `test_win32_prefix_applies_to_bytes_patterns` (`usefixtures("win32")`):
   `AccessRulePattern.pattern_to_regex(b"/A")[0].startswith(b"(?i)")`.
   Also assert `GlobPattern.pattern_to_regex("A")[0].startswith("(?i)")`.
   Import both classes.
6. `test_rule_semantics_unchanged` (no platform patch):
   - `_load(tmp_path, "read-only /a[b\n").problems == ()` (an unclosed `[` is still valid);
   - `_load(tmp_path, "read-only config/*\n").match("config/sub/x.json") is None`.
   Use separate `tmp_path` subdirectories, or two tests, since `_load` writes
   the same file.

Tests 2, 3 and 4 (`[Z-a]x`, `[A-z]x`) fail before the change. Everything
else in the file must keep passing.

## Docs — `docs/ARCHITECTURE.md`

Replace "matches with `PathSpec.from_lines("gitignore", …)`, last match wins"
with "matches with `PathSpec.from_lines(AccessRulePattern, …)` (gitignore
semantics; case-insensitive on win32 through a `(?i)` regex prefix, not by
lower-casing), last match wins".

## Commit

`fix(access_rules): case-insensitive patterns via (?i), report re.error (#405)`
