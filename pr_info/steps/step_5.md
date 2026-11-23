# Step 5 — Server instructions sentence (gap 4)

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement **only** `pr_info/steps/step_5.md`.
> Write the test first, then the change. Run pylint, pytest (`-n auto`) and mypy until all pass,
> run `run_format_code`, and make exactly one commit.

## Goal

The server instructions say, in one sentence, that gitignored paths are refused unless
`.mcp-file-access` exposes them, that rules can make paths read-only, and that the agent cannot
change the rules file.

## WHERE

- `src/mcp_workspace/server.py` — `_INSTRUCTIONS`
- `tests/test_server_instructions.py`

## WHAT

Append this sentence to `_INSTRUCTIONS`, with a leading space:

`Gitignored paths are refused unless the project's .mcp-file-access exposes them; its rules can
also make paths read-only, and only the user can change that file.`

## HOW

- The phrase "only the user can change that file" tells the agent it cannot change the file without
  inviting it to try native tools.
- The sentence contains no `github_`, no reference tool names, and no slash after whitespace, so the
  existing `test_server_instructions_describe_reference_projects` keeps passing.

## ALGORITHM / DATA

None.

## Tests (write first) — `tests/test_server_instructions.py`

Add `test_server_instructions_mention_access_rules(tmp_path)`:
- `text = create_server(tmp_path).instructions`
- assert `".mcp-file-access" in text`, `"read-only" in text`, `"only the user can change" in text`.

## Commit

`docs(server): mention .mcp-file-access in server instructions (#404)`
