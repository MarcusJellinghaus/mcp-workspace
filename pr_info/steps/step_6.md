# Step 6 — Docs: README and release notes

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement **Step 6** exactly as described in `pr_info/steps/step_6.md`. Documentation only. Run pylint, pytest (`-n auto`) and mypy via the MCP tools to confirm nothing broke. Run `run_format_code`, then make one commit.

## Precondition

Steps 1-5 are done (`--read-max-lines` exists in `main.py`). If not, write one line to `pr_info/.blocked.txt` and stop.

## WHERE

- `README.md`
- `docs/release-notes.md`

## WHAT / HOW

Read each target section first; match the surrounding style and keep additions short.

- `README.md`
  - Usage line (~line 81): add `[--read-max-lines N]` next to `--file-size-limit`.
  - CLI arguments (~84-92): one bullet — `--read-max-lines`: maximum lines a full `read_file` / `read_reference_file` returns (default 2000, `0` = no limit); overrides `config.toml`.
  - Config section (~100-117): new `[mcp_workspace]` subsection with a TOML example `read_max_lines = 2000`, one sentence: read once at startup; `0` = no limit; invalid values are ignored with a warning; the CLI flag wins.
  - Tool summaries (~48 `read_file`, ~57 `read_reference_file`): one sentence each — full reads are cut at the configured limit with a note giving the next `start_line` / `end_line`; explicit ranges are returned in full.
- `docs/release-notes.md`: one entry under the unreleased/next section: full reads in `read_file` / `read_reference_file` are capped (default 2000 lines; `--read-max-lines` / `[mcp_workspace] read_max_lines`; `0` disables); `file_tools.DEFAULT_READ_MAX_LINES` exported for library callers.

## ALGORITHM / DATA

None.

## Tests

None (docs only); the existing suite must still pass.
