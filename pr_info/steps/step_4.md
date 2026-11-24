# Step 4 — `main.py`: reference validation split and `verify` dispatch

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_4.md`.
> Follow TDD: extend `tests/test_main_validate_reference_projects.py` and write
> `tests/test_main_verify.py` first, then change `src/mcp_workspace/main.py`.
> Keep the server parser and its `parse_known_args` behaviour unchanged; keep
> the diff to `validate_reference_projects`'s loop minimal. Import
> `mcp_workspace.cli.verify` lazily inside the verify branch only. Run all
> checks listed below (including the serial performance run) and make exactly
> one commit.

## WHERE

- Modify `src/mcp_workspace/main.py`.
- Modify `tests/test_main_validate_reference_projects.py`.
- Create `tests/test_main_verify.py`.

## WHAT

```python
from mcp_workspace.utils.url_credentials import scrub_credentials

def _add_reference_project_argument(parser: argparse.ArgumentParser) -> None: ...
def _check_reference_projects(
    reference_args: list[str], project_dir: Path
) -> tuple[dict[str, ReferenceProject], list[tuple[str, str]]]: ...
def validate_reference_projects(
    reference_args: list[str], project_dir: Path
) -> dict[str, ReferenceProject]: ...            # thin wrapper: return _check_reference_projects(...)[0]
def _verify_parser() -> argparse.ArgumentParser: ...
def _verify_main(argv: list[str]) -> int: ...
def main() -> None: ...                           # dispatch added
```

### `_add_reference_project_argument`
Moves the existing `--reference-project` definition (`action="append"`, same
help text) out of `parse_args`; both `parse_args` and `_verify_parser` call it.

### `_check_reference_projects`
The current body of `validate_reference_projects`, plus a local
`rejected: list[tuple[str, str]]`. Before each existing `continue`, append
`(scrub_credentials(label), reason)`:

| Branch | label | reason |
|---|---|---|
| old format | raw `arg` | `old format` |
| missing name | raw `arg` | `missing name` |
| missing path | `name` | `missing path` |
| path does not exist, no `url` | `name` | `path not found` |
| not a directory | `name` | `not a directory` |
| same as project dir | `name` | `same directory as workspace` |
| subdirectory of project dir | `name` | `inside workspace` |
| parent of project dir | `name` | `parent of workspace` |

In the `old format`, `missing name` and `missing path` warnings pass
`scrub_credentials(arg)` instead of `arg`. All other log text unchanged. URL
mismatch still raises `ValueError`. Returns `(validated_projects, rejected)`;
empty input → `({}, [])`.

### `_verify_parser`
`argparse.ArgumentParser(prog="mcp-workspace verify", description=..., allow_abbrev=False)`
(plain argparse → usage errors exit 2):
- `--project-dir` (default `None`, help: defaults to the current directory);
- `--reference-project` via `_add_reference_project_argument`;
- `--log-level`, `type=str.upper`, `choices=_LOG_LEVELS`, `default="WARNING"`.

### Server parser
Add `epilog="Run 'mcp-workspace verify --help' to check file access, git and GitHub setup."`
to the `StartupArgumentParser` in `parse_args`.

## ALGORITHM

```
def main():
    argv = sys.argv[1:]
    if argv[:1] == ["verify"]: sys.exit(_verify_main(argv[1:]))   # before _main / _HELP_TOKENS
    try: _main() except Exception as exc: _handle_startup_failure(exc); sys.exit(1)   # unchanged

def _verify_main(argv):
    for stream in (sys.stdout, sys.stderr): if isinstance(stream, io.TextIOWrapper): stream.reconfigure(encoding="utf-8")
    args = _verify_parser().parse_args(argv)                      # SystemExit(0/2) propagates
    try:
        setup_logging(args.log_level, None)                       # console (stderr) only
        project_dir = _resolve_project_dir(args.project_dir or str(Path.cwd()))
        if project_dir is None: raise ValueError(f"--project-dir must be an existing directory: {args.project_dir!r}")
        valid, rejected = _check_reference_projects(args.reference_project or [], project_dir)
        from mcp_workspace.cli.verify import execute_verify
        return execute_verify(project_dir, valid, rejected)
    except Exception as exc: print(f"Error: {exc}", file=sys.stderr); return 1   # no fallback log file
```

`_main` change: move `args, unknown = parse_args(argv)` to directly after
`stdlogger.debug("Logger initialized in main")` and before the
`if project_dir is None` check, then add
`if "verify" in unknown: raise ValueError("verify must be the first argument")`
before that check. Use the existing `_main` reference-project call
(`validate_reference_projects`) unchanged.

## DATA

- Rejected entries: `list[tuple[str, str]]` = `(label, reason)`, labels scrubbed.
- `_verify_main` return: exit code `0`/`1`; argparse exits `2` (usage) or `0` (`--help`).

## Tests (write first)

`tests/test_main_validate_reference_projects.py` — add tests on
`_check_reference_projects` (patching `mcp_workspace.main.Path.exists`,
`mcp_workspace.main.Path.is_dir`, `mcp_workspace.main.detect_and_verify_url`,
as the existing tests do):
- each of the eight reasons with its label;
- accepted duplicates appear under auto-renamed keys (`proj`, `proj_2`) and not in `rejected`;
- `validate_reference_projects` still returns only the valid dict;
- a credential in a rejected argument (`path=/x,url=https://user:tok@github.com/o/r`
  with missing name) is scrubbed in the label **and** in the logged warning
  (patch `mcp_workspace.main.stdlogger`; assert `tok` absent from call args).

`tests/test_main_verify.py`:
- `verify` dispatch: patch `mcp_workspace.cli.verify.execute_verify` to return
  0/1; set `sys.argv = ["mcp-workspace", "verify", "--project-dir", str(tmp_path)]`;
  `pytest.raises(SystemExit)` with matching code; `execute_verify` receives the
  resolved project dir, valid dict and rejected list.
- `--project-dir` omitted → current directory (`monkeypatch.chdir(tmp_path)`).
- `--project-dir` not an existing directory → exit 1, `Error: …` on stderr,
  no `logs/mcp_workspace_startup_error.log` created (chdir to `tmp_path`).
- `execute_verify` raising → exit 1, `Error: …`.
- URL mismatch (`detect_and_verify_url` raising `ValueError`) → exit 1, `Error: …`.
- unknown option after verify (`verify --log-file x`) → exit 2.
- `--log-level debug` accepted (upper-cased); `--log-level nope` → exit 2.
- `verify --help` → exit 0, stdout contains `mcp-workspace verify`
  and `--reference-project`, not the server description.
- server `--help` output mentions `verify` (epilog).
- verify not first (`--project-dir <tmp> verify`, and `--log-level DEBUG verify`
  without project dir) → `_main` raises `ValueError("verify must be the first argument")`.
- stray positional (`--project-dir <tmp> stray`) still starts the server:
  patch `mcp_workspace.server.run_server`, assert it was called and a warning
  about `stray` was logged.
- import guard: in a fresh subprocess (`sys.executable -c`, `PYTHONPATH` = `src`
  first, as in `tests/test_startup_performance.py`) run
  `import mcp_workspace.main` and assert none of `git`, `github`, `yaml`,
  `mcp_workspace.cli` is in `sys.modules`.

Existing tests in `tests/test_main.py` and `tests/test_startup.py` must still
pass; if one asserts the old ordering of parse errors vs. the
`--project-dir` check, update it to the new ordering.

## Checks (all must pass)

`run_format_code`, `run_ruff_check`, `run_pylint_check`, `run_mypy_check`,
`run_pytest_check(extra_args=["-n", "auto"])`,
`run_pytest_check(markers=["performance"], extra_args=["-n", "0"])`,
`run_lint_imports_check`, `run_tach_check`, `run_vulture_check`.

## Commit

`feat(main): add mcp-workspace verify subcommand`
