# Decisions Log — Issue #184 Plan Update

## D1 (MAJOR) — Path resolver lives in `mcp-coder-utils`, not in `mcp_workspace`

**Decision:** "Add to mcp-coder-utils first" — `mcp_workspace` will import a
public path-resolver from `mcp_coder_utils`. No local helper.

**Implication:** This PR has an upstream prerequisite. An issue/PR must be
filed at https://github.com/MarcusJellinghaus/mcp-coder-utils first; this
PR cannot merge until that release is available and `pyproject.toml` has
been bumped accordingly.

**Suggested upstream API** (final naming to be agreed in the upstream PR):

```python
from mcp_coder_utils.user_config import get_user_config_path
```

**Investigation findings (`mcp-coder-utils` reference project):**

- Existing modules: `log_utils`, `redaction`, `subprocess_runner`,
  `subprocess_streaming`, plus an `fs/` subpackage.
- No `config/` module and no path helper exists yet.
- `__init__.py` only exports `__version__`.
- The canonical implementation already lives in `mcp_coder` itself at
  `src/mcp_coder/utils/user_config.py:160` as `get_config_file_path()`.
  Suggest mirroring that source-name into a new
  `mcp_coder_utils/user_config.py` module, with the public function
  renamed to `get_user_config_path` for clarity at downstream call sites.

## F1 (Boy Scout) — Update `config.py:10` docstring too

Replace `"""Read a value from ~/.mcp_coder/config.toml."""` with
`"""Read a value from the user config file."""` in Step 1.

## F4 (Step 2 grep gate) — Reword to avoid Step 3 false positives

Step 2's acceptance previously demanded "no occurrences of
`~/.mcp_coder/config.toml`" in `base_manager.py` / `verification.py`.
That would fire on the dual-path docstrings Step 3 introduces. Reworded
Step 2 to scope the grep to non-docstring lines and explicitly defer the
comprehensive repo-wide grep gate to Step 3.

## F7 (MCP tool namespace) — Use `mcp__mcp-tools-py__*`

All tool references in `summary.md` and step files were updated from the
incorrect `mcp__tools-py__run_*` to `mcp__mcp-tools-py__run_*` per
`.claude/CLAUDE.md`.

## F8 (Formatter) — Use MCP tool, not shell script

All step "LLM Prompt" sections referencing `./tools/format_all.sh` were
updated to `mcp__mcp-tools-py__run_format_code` per `.claude/CLAUDE.md`.

## Skipped (no action this round)

F2, F3, F5, F6, F9, F10 — confirmations or borderline test additions
deferred to keep the plan minimal.
