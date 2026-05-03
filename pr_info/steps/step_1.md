# Step 1 — Add `split_args_pathspec` helper and reword `validate_args` error

> See `pr_info/steps/summary.md` for the full design rationale and architectural overview.

## Goal
Introduce the validation/transform helper and metadata move. After this step the helper exists, has full unit tests, and `validate_args`'s `--` rejection wording is updated — but no handler is using the helper yet (handler wiring is Step 2).

## WHERE
- `src/mcp_workspace/git_operations/arg_validation.py` — add `_SUPPORTS_PATHSPEC`, add `split_args_pathspec`, reword `validate_args`'s `--` rejection.
- `src/mcp_workspace/git_operations/read_operations.py` — remove local `_SUPPORTS_PATHSPEC` definition (~line 407); import from `arg_validation`.
- `tests/git_operations/test_arg_validation.py` — update `test_rejects_double_dash`; add `TestSplitArgsPathspec` class.

## WHAT

### `_SUPPORTS_PATHSPEC` (new constant in `arg_validation.py`)
```python
_SUPPORTS_PATHSPEC: frozenset[str] = frozenset(
    {"log", "diff", "show", "status", "ls_tree", "ls_files"}
)
```

### `split_args_pathspec` (new function in `arg_validation.py`)
```python
def split_args_pathspec(
    command: str,
    args: list[str],
    pathspec: list[str] | None,
) -> tuple[list[str], list[str] | None]:
    """Split args on '--' for pathspec commands; route tail into pathspec.

    Returns (args, pathspec) unchanged for commands not in
    _SUPPORTS_PATHSPEC or when '--' is absent. For pathspec commands,
    splits on the first '--', routes the tail into pathspec, and
    raises ValueError on multi-'--' or conflict-with-explicit-pathspec.
    """
```

### `validate_args` (existing — reword only)
Replace the `--` rejection branch:
```python
# BEFORE
if "--" in args:
    msg = (
        "Flag '--' is not allowed in args. "
        "Use the 'pathspec' parameter instead."
    )
    raise ValueError(msg)

# AFTER
if "--" in args:
    raise ValueError(f"git {command} does not accept '--'")
```

## HOW
- `read_operations.py` keeps using `_SUPPORTS_PATHSPEC` for its dispatcher's soft-warning logic — change the import to `from .arg_validation import _SUPPORTS_PATHSPEC`. No re-export shim needed.
- `split_args_pathspec` is a pure function — input → output, no I/O, no mutation of inputs.
- Helper is **not yet called** from any handler in this step.

## ALGORITHM
```
if command not in _SUPPORTS_PATHSPEC or "--" not in args:
    return args, pathspec
idx = args.index("--")
head, tail = args[:idx], args[idx + 1 :]
if "--" in tail:                      raise "Multiple '--' tokens in args are not allowed."
if pathspec is not None and tail:     raise "Specify paths via either '--' in args or the 'pathspec' parameter, not both."
return head, (tail or pathspec)
```

## DATA
- Returns `tuple[list[str], list[str] | None]`.
- Empty tail with no explicit pathspec: `(["--"], None)` → `([], None)`.
- Empty tail with explicit pathspec: `(["--"], ["x"])` → `([], ["x"])` (preserved).
- Conflict / multi-`--`: raises `ValueError`.

## Tests (TDD: write FIRST, before the helper)

### Update existing test in `TestValidateArgsRejected`
```python
def test_rejects_double_dash(self) -> None:
    with pytest.raises(ValueError, match="merge_base does not accept"):
        validate_args("merge_base", ["--"])
```

### Add new class `TestSplitArgsPathspec`
```python
from mcp_workspace.git_operations.arg_validation import split_args_pathspec

class TestSplitArgsPathspec:
    def test_no_op_for_non_pathspec_command(self) -> None:
        # merge_base does not support pathspec — args returned unchanged
        assert split_args_pathspec("merge_base", ["--", "x"], None) == (["--", "x"], None)

    def test_no_op_when_no_double_dash(self) -> None:
        assert split_args_pathspec("log", ["--oneline"], None) == (["--oneline"], None)

    def test_split_with_one_path(self) -> None:
        assert split_args_pathspec("diff", ["main", "--", "README.md"], None) == (
            ["main"], ["README.md"]
        )

    def test_split_with_multiple_paths(self) -> None:
        assert split_args_pathspec("log", ["--", "a.py", "b.py"], None) == (
            [], ["a.py", "b.py"]
        )

    def test_empty_tail_is_noop(self) -> None:
        assert split_args_pathspec("log", ["--"], None) == ([], None)

    def test_empty_tail_preserves_explicit_pathspec(self) -> None:
        assert split_args_pathspec("log", ["--"], ["x"]) == ([], ["x"])

    def test_multiple_double_dash_rejected(self) -> None:
        with pytest.raises(ValueError, match="Multiple '--'"):
            split_args_pathspec("diff", ["--", "a", "--", "b"], None)

    def test_conflict_with_explicit_pathspec_rejected(self) -> None:
        with pytest.raises(ValueError, match="either '--' in args or the 'pathspec'"):
            split_args_pathspec("diff", ["--", "x"], ["y"])

    def test_preserves_pathspec_when_no_double_dash(self) -> None:
        assert split_args_pathspec("log", ["main"], ["README.md"]) == (
            ["main"], ["README.md"]
        )
```

## Code-quality gate (mandatory after edits)
All three must pass:
```
mcp__tools-py__run_pylint_check
mcp__tools-py__run_pytest_check  (extra_args=["-n", "auto", "-m",
    "not git_integration and not claude_cli_integration and not claude_api_integration "
    "and not formatter_integration and not github_integration and not langchain_integration"])
mcp__tools-py__run_mypy_check
```

## LLM Prompt

> Read `pr_info/steps/summary.md` and `pr_info/steps/step_1.md`.
>
> Implement Step 1: in `src/mcp_workspace/git_operations/arg_validation.py` add the `_SUPPORTS_PATHSPEC` constant and the `split_args_pathspec` helper, and reword the `--` rejection in `validate_args` to `f"git {command} does not accept '--'"`. In `src/mcp_workspace/git_operations/read_operations.py`, replace the local `_SUPPORTS_PATHSPEC` definition with `from .arg_validation import _SUPPORTS_PATHSPEC`.
>
> Follow TDD: first write the test updates in `tests/git_operations/test_arg_validation.py` exactly as listed in the Tests section (update `test_rejects_double_dash`, add `TestSplitArgsPathspec` class with all listed test methods). Then implement the helper to make them pass.
>
> Use only MCP tools (`mcp__workspace__*` for files, `mcp__tools-py__run_*` for checks). Run pylint, fast pytest (with the no-integration marker filter), and mypy — all must pass before completing. Do NOT wire the helper into any handler in this step (that is Step 2).
>
> This step must produce exactly one commit.

## Done when
- All tests in `tests/git_operations/test_arg_validation.py` pass.
- Pylint, fast pytest, and mypy are all green.
- `read_operations.py` no longer defines `_SUPPORTS_PATHSPEC` locally.
- One commit produced.
