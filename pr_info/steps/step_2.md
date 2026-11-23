# Step 2 — `git log` pickaxe flags

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement **only** `pr_info/steps/step_2.md`.
> Write the tests first, then the implementation. Use the MCP tools from `.claude/CLAUDE.md`.
> Run pylint, pytest (`extra_args: ["-n", "auto"]`) and mypy; all must pass. Run
> `run_format_code`, then make exactly one commit for this step.

## WHERE

- `src/mcp_workspace/git_operations/arg_validation.py`
- `tests/git_operations/test_arg_validation.py`
- `tests/git_operations/test_read_operations.py`

## WHAT

- `LOG_ALLOWED_FLAGS` += `"-S"`, `"-G"`, `"--pickaxe-regex"`, `"--pickaxe-all"`.
- `_ATTACHED_VALUE_FLAGS["log"]` += `"-S": _ANY_VALUE`, `"-G": _ANY_VALUE` with
  `_ANY_VALUE = re.compile(r".+", re.DOTALL)` (non-empty, multi-line allowed).
- `validate_args`: before the generic allowlist check, a bare `-S` / `-G` for `log` raises
  `ValueError("git log: '-S' needs its value attached, e.g. '-SLINKED_VIA_PR' (separate form is not accepted)")`
  (same wording with `-G` / `-G<regex>`).

## HOW

`_short_cluster_allowed` already hands the remainder of the cluster to the attached-value
pattern, so `-SLINKED_VIA_PR` passes through it unchanged. A bare `-S` has an empty
remainder, which `.+` rejects; the new branch turns that into the attached-form error.
`positional_args` already skips `-S…` (it starts with `-`), so the value is never path-checked.

## ALGORITHM (validate_args addition)

```
for arg in args:
    if command == "log" and arg in ("-S", "-G"):
        raise ValueError(<attached-form message naming arg>)
    ... existing check ...
```

## Tests (write first)

- `validate_args("log", ["-Sfoo"])`, `["-Gfo+o"]`, `["-Sline1\nline2"]`, `["-Sfoo", "--pickaxe-all"]`,
  `["-Gx", "--pickaxe-regex"]` pass.
- `validate_args("log", ["-S", "foo"])` raises `ValueError` whose message contains `-S<` or
  `'-SLINKED_VIA_PR'` (the attached form) and not "security allowlist"; same for `-G`.
- `validate_args("diff", ["-Sfoo"])` still rejected (log only).
- Integration (`test_read_operations.py`, real repo): commit a file containing `NEEDLE`, then
  `git(command="log", project_dir=repo, args=["-SNEEDLE", "--oneline"])` lists that commit;
  `-GNEE.LE` likewise.
