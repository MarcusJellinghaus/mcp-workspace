# Step 5 — Documentation

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_5.md`.
> Documentation only; no code changes. Keep `README.md` at or under 750 lines
> (do not add it to `.large-files-allowlist`). Run the checks listed below and
> make exactly one commit.

## WHERE

- Create `docs/verify.md`.
- Modify `README.md`, `docs/ARCHITECTURE.md`, `docs/file-access.md`,
  `docs/release-notes.md`.

## WHAT

### `docs/verify.md`
Short user doc (no tests apply):
- Purpose: check a setup without mcp_coder, or in CI; same format as `mcp-coder verify`.
- Usage line:
  `mcp-workspace verify [--project-dir DIR] [--reference-project name=<name>,path=<dir>[,url=<url>]]... [--log-level LEVEL]`.
  All options come after `verify`; `verify` must be the first argument.
- Defaults: `--project-dir` = current directory; `--log-level WARNING`;
  console logging only (stderr); git signing is tested end-to-end
  (`actually_sign`, gpg only, 15 s timeout).
- Sections: FILE ACCESS (one row per project: `workspace`, accepted
  references, rejected references; the example table from the summary),
  GIT, GITHUB, GITHUB SECURITY (exit-neutral).
- Rejected-reference reasons (the eight phrases) and that a reference with
  `url=` but a missing path shows `[WARN] path not found` without failing.
- Exit codes: 0 / 1 / 2 as in the summary.
- CI note: without a GitHub token (`GITHUB_TOKEN` or `[github] token` in
  `config.toml`) `Token configured` is `[ERR]`, so `verify` exits 1.
- `verify` prints `Error: …` to stderr on setup errors and does **not** write
  `logs/mcp_workspace_startup_error.log`.

### `README.md`
- Line ~96 ("Unrecognized arguments are ignored at startup …"): add that the
  exception is `verify`, which is only accepted as the first argument and
  otherwise stops startup with an error.
- After the startup-errors sentence (~line 98) add one line:
  `` `mcp-workspace verify` checks file access, git and GitHub setup from the command line — see [docs/verify.md](docs/verify.md). ``

### `docs/ARCHITECTURE.md`
- Layer diagram: add `cli/` beside `MCP Server (server.py)` (e.g.
  `MCP Server (server.py)  │  CLI checks (cli/)`).
- Layer Responsibilities table: add row
  `| **CLI** | `mcp-workspace verify`: runs file-access, git and GitHub checks and formats the sections (`cli/verify_formatting.py` is imported by mcp_coder) | Tools, Utilities, `mcp_coder_utils.verify_render` |`.
- Library Isolation table: add row
  `| `yaml` (PyYAML) | github_operations/security_rows.py | Local dependabot / CodeQL workflow checks |`.
- Section 4 (lazy imports): one sentence that `main.py` imports `cli.verify`
  only inside the verify branch, guarded by `tests/test_main_verify.py`.

### `docs/file-access.md`
Line ~96 ("To check a rules file by hand, …"): add `run mcp-workspace verify`
(checks the workspace and every reference project) as the first option.

### `docs/release-notes.md`
New top section `## Next minor release — mcp-workspace verify (#409)` with bullets:
- new `mcp-workspace verify` command (sections, options, exit codes, link to `verify.md`);
- `mcp-workspace … verify` (not first) now fails at startup with `verify must be the first argument`;
- new public API: `mcp_workspace.cli.verify_formatting` (`format_git_section`,
  `format_github_section`, `format_github_security_section`,
  `format_file_access_section`), `mcp_workspace.github_operations.github_security_rows`;
- reference-project warnings no longer show credentials embedded in the raw argument;
- PyYAML is now a runtime dependency.

## Checks (all must pass)

`check_file_size` (README ≤ 750 lines), `run_pytest_check(extra_args=["-n", "auto"])`.

## Commit

`docs: document mcp-workspace verify`
