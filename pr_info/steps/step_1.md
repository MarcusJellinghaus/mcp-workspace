# Step 1 — Simplify `read_gitignore_rules` return type and reduce log verbosity

Implements all of Issue #48. See [summary.md](./summary.md) for the design
rationale. Single commit: tests + implementation + all checks green.

## WHERE

| File | Change |
|---|---|
| `tests/file_tools/test_directory_utils.py` | Update 2 existing tests; add 1 new test |
| `src/mcp_workspace/file_tools/directory_utils.py` | Rewrite `read_gitignore_rules`; drop `Tuple` import; update 2 call sites |

No new modules, no new folders, no changes to `file_tools/__init__.py`
(`read_gitignore_rules` is not in its `__all__`).

## WHAT

Signature change on the one function:

```python
# before  (directory_utils.py, current line 80)
def read_gitignore_rules(
    gitignore_path: Path,
) -> Tuple[Optional[Callable[[str], bool]], Optional[str]]: ...

# after
def read_gitignore_rules(
    gitignore_path: Path,
) -> Optional[Callable[[str], bool]]: ...
```

Unchanged signatures: `is_path_gitignored`, `apply_gitignore_filter`,
`filter_with_gitignore`, `list_files`, `is_path_in_git_dir`.

## HOW — Integration Points

1. **Import (current line 10).** Remove `Tuple` from
   `from typing import Callable, List, Optional, Tuple, Union`. `Tuple` occurs
   exactly twice in the file — the import and the return annotation — so it
   becomes unused. `Callable`, `Optional`, `List`, `Union` all remain in use.
2. **Call site — `is_path_gitignored` (current line 47).**
   `matcher, _ = read_gitignore_rules(...)` → `matcher = read_gitignore_rules(...)`
3. **Call site — `filter_with_gitignore` (current line 175).** Same edit.
4. **Logger.** Reuse the module-level `logger` at line 16. No new logger, no
   config changes.

## ALGORITHM

```
if gitignore file does not exist:
    log DEBUG "No .gitignore file found at <path>"; return None
try:
    parser = IgnoreParser(); parser.parse_rule_file(path)
    log DEBUG "Loaded .gitignore at <path> (<len(parser.rules)> rules)"   # AFTER parse
    return closure wrapping parser.match in bool()
except Exception:
    log WARNING (unchanged message); return None
```

Target implementation:

```python
def read_gitignore_rules(gitignore_path: Path) -> Optional[Callable[[str], bool]]:
    """Read and parse a .gitignore file to create a matcher function.

    Args:
        gitignore_path: Path to the .gitignore file

    Returns:
        A matcher function, or None if the file doesn't exist or cannot be parsed
    """
    if not gitignore_path.is_file():
        logger.debug("No .gitignore file found at %s", gitignore_path)
        return None

    try:
        parser = IgnoreParser()
        parser.parse_rule_file(gitignore_path)
        logger.debug(
            "Loaded .gitignore at %s (%s rules)", gitignore_path, len(parser.rules)
        )

        # Create a matcher function that mimics the behavior of the old parse_gitignore
        def matcher(path: str) -> bool:
            return bool(parser.match(path))

        return matcher

    except Exception as e:  # pylint: disable=broad-except
        logger.warning("Error reading/parsing gitignore: %s", str(e))
        return None
```

### Constraints — do not deviate

- The DEBUG summary must come **after** `parse_rule_file`. `IgnoreParser.__init__`
  sets `self.rules = list()`; the list is only populated during parsing.
- Keep the `bool(...)` wrapper. Existing tests assert `matcher(f) is True` /
  `is False` (identity, not truthiness), so returning `parser.match` bare would
  fail them.
- Keep `try`/`except`. `parse_rule_file` opens the file itself, so I/O and parse
  errors remain live even though the explicit read is gone.
- Message text is exactly `"Loaded .gitignore at %s (%s rules)"` — "rules", not
  "patterns"; see summary.md for why.
- Do **not** add parser caching. Out of scope per the issue.
- The `# Create a matcher function that mimics the behavior of the old
  parse_gitignore` comment references a function no longer present in the repo.
  It is retained above to keep the diff inside the issue's scope; delete it only
  if the reviewer asks.

## DATA — Return Values

| Path through the function | Before | After |
|---|---|---|
| `.gitignore` missing | `(None, None)` | `None` |
| Parse succeeds | `(matcher, content_str)` | `matcher` |
| Exception raised | `(None, None)` | `None` |

Three `return` statements change (current lines 93, 111, 115). Callers already
branch on `if matcher is None`, so no caller logic changes — only the unpacking.

`matcher` is `Callable[[str], bool]` taking an **absolute** path string; both
call sites build it as `str(project_dir / path)`. Unchanged.

## TDD Sequence

### Red — write tests first

**a. `test_read_gitignore_rules_no_file` (current lines 147-158).** Change the
unpack to `matcher = read_gitignore_rules(temp_path)`. Delete
`assert content is None` and reword the now-inaccurate `# Both should be None
when file doesn't exist` comment to refer to the matcher alone.

**b. `test_read_gitignore_rules_with_file` (current lines 161-186).** Change the
unpack to `matcher = read_gitignore_rules(temp_path)`. Delete the
`# Content should match what we wrote` comment and `assert content ==
gitignore_content`. Keep the local `gitignore_content` — it is still used by
`temp_path.write_text(...)`. Keep the `callable(matcher)` and both
`matcher(...) is True/False` assertions.

**c. New regression test — guards the actual defect.** Asserts no INFO-or-above
records escape, without pinning message text (brittle):

```python
def test_read_gitignore_rules_logs_nothing_above_debug(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The gitignore hot path emits no INFO+ records (issue #48)."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir) / ".gitignore"

        with caplog.at_level(
            logging.INFO, logger="mcp_workspace.file_tools.directory_utils"
        ):
            read_gitignore_rules(temp_path)  # absent-file path
            temp_path.write_text("*.log\n")
            read_gitignore_rules(temp_path)  # parsed-file path

        assert caplog.records == []
```

Requires `import logging` and `import pytest` in the test module — verify whether
they are already present before adding.

> This test is **beyond the issue's literal list**, which names only the two
> assertion updates. It is 10 lines and encodes the issue's actual goal rather
> than its mechanics. Drop it if the reviewer prefers a strictly minimal diff;
> the rest of the step stands without it.

**Expected failures before implementation:** (a) `matcher` is `(None, None)`, so
`assert matcher is None` fails. (b) `matcher` is a tuple, so `assert
callable(matcher)` fails. (c) three INFO records captured, so `caplog.records`
is non-empty.

### Green — implement

Apply the HOW and ALGORITHM sections above.

### Verify

Run all three MCP checks. Mypy is the decisive one: it flags any surviving tuple
unpack of the new `Optional[Callable]` return.

```
mcp__tools-py__run_mypy_check()
mcp__tools-py__run_pylint_check()
mcp__tools-py__run_pytest_check(extra_args=["-n", "auto", "-m", "not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"])
```

Then run `./tools/format_all.sh` before committing, per CLAUDE.md.

## Acceptance Criteria

- [ ] `read_gitignore_rules` returns `Optional[Callable[[str], bool]]`
- [ ] Explicit `open()/read()` of `.gitignore` deleted; no `gitignore_content` local remains
- [ ] `Tuple` removed from the `typing` import
- [ ] Both call sites use plain assignment, not tuple unpacking
- [ ] All three `return None, None` replaced with `return None`
- [ ] Docstring `Returns:` describes a single value
- [ ] No INFO-level logging remains in `read_gitignore_rules`
- [ ] Pylint, pytest, and mypy all pass

## LLM Prompt

> Implement Step 1 of Issue #48 in the `mcp-coder-dev` project.
>
> Read `pr_info/steps/summary.md` for design rationale and
> `pr_info/steps/step_1.md` for the full specification, then implement exactly
> what step_1.md describes — no more.
>
> **Follow `.claude/CLAUDE.md` strictly: use `mcp__workspace__*` tools for all
> file operations and `mcp__tools-py__*` tools for all quality checks. Never use
> `Read`, `Write`, `Edit`, or `Bash` for these.**
>
> Work test-first: apply the three test changes in the "TDD Sequence" section of
> step_1.md, confirm they fail for the stated reasons, then apply the
> implementation from the ALGORITHM section.
>
> The scope is one function (`read_gitignore_rules`), one import line, two call
> sites, and one test file — roughly 10 changed lines. Do not add parser caching,
> do not change `is_path_gitignored` or `apply_gitignore_filter`, and do not
> touch `file_tools/__init__.py`. Honour the "Constraints — do not deviate"
> subsection, in particular the exact log message wording and the requirement
> that the DEBUG summary is emitted after `parse_rule_file`.
>
> Finish by running pylint, pytest, and mypy via the MCP tools and reporting the
> results. If any check fails, fix it before reporting completion. This step is
> one commit.
