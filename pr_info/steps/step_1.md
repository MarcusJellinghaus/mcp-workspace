# Step 1 — `run_git_timed` names the command after leading `-c` pairs

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement **only** `pr_info/steps/step_1.md`.
> Write the tests first, then the implementation. Use the MCP tools from `.claude/CLAUDE.md`.
> Run pylint, pytest (`extra_args: ["-n", "auto"]`) and mypy; all must pass. Run
> `run_format_code`, then make exactly one commit for this step.

## WHERE

- `src/mcp_workspace/git_operations/_subprocess_git.py`
- `tests/git_operations/test_subprocess_git.py`

## WHAT

```python
def _subcommand_name(args: tuple[str, ...]) -> str:
    """Return the git subcommand, skipping leading ``-c key=value`` pairs."""
```

`run_git_timed` uses it instead of `args[0]` for the debug log and for the error texts
(`"git {sub} timed out after {t:g} s"`, `"git {sub} could not run: …"`,
`"git {sub} failed (exit N)"`).

## ALGORITHM

```
i = 0
while i + 1 < len(args) and args[i] == "-c":
    i += 2
return args[i] if i < len(args) else ""
```

## DATA

Unchanged `GitOutput`; only the command name in `error` changes when `-c` pairs lead.

## Tests (write first)

- `_subcommand_name(("-c", "a=b", "-c", "c=d", "fetch", "origin")) == "fetch"`.
- `_subcommand_name(("push",)) == "push"`, `_subcommand_name(()) == ""`.
- `run_git_timed(tmp, "-c", "gc.auto=0", "fetch", …)` with `subprocess.run` mocked to raise
  `TimeoutExpired` → `error == "git fetch timed out after 10 s"`, `returncode is None`.
- Same with a mocked non-zero exit → `error == "git fetch failed (exit 1)"`.
