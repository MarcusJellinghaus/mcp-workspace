# Step 2 — Exclude `TYPE_CHECKING` imports in import-linter, drop the `base_branch` waivers

Read `pr_info/steps/summary.md` first.

One commit: `chore(importlinter): exclude TYPE_CHECKING imports, drop base_branch waivers`

Independent of step 1 — the two can be committed in either order. There is no code change and
no new test in this step; the check tools *are* the test.

## WHERE

| Path | Action |
|---|---|
| `.importlinter` | modify — session options block and the layered contract |

Nothing else. `tach.toml` already sets `ignore_type_checking_imports = true` and stays as is.

## WHAT

### 1. Add the session option

In the `[importlinter]` block (currently `root_packages`, `root_package_paths`,
`include_external_packages`), add `exclude_type_checking_imports = True` with a comment
recording the trade-off:

```ini
[importlinter]
root_packages =
    mcp_workspace
    tests
root_package_paths =
    src
    .
include_external_packages = True
# Match tach's ignore_type_checking_imports, so an annotation-only import is not
# reported as a dependency. The flag applies at graph-build time, so it governs
# all nine contracts - including the six library-isolation ones and the
# subprocess ban, which depend on external edges (include_external_packages).
# Trade-off: a forbidden library import hidden inside a TYPE_CHECKING guard
# would no longer be flagged. Nothing changes today - the only upward
# TYPE_CHECKING imports in src/ are base_branch's two, and no module
# type-checking-imports github/git/mcp/requests/subprocess outside its allowed
# home.
exclude_type_checking_imports = True
```

### 2. Delete both waivers

In `[importlinter:contract:layered_architecture]`, remove the whole `ignore_imports` key and
its two entries:

```ini
ignore_imports =
    mcp_workspace.git_operations.base_branch -> mcp_workspace.github_operations.issues
    mcp_workspace.git_operations.base_branch -> mcp_workspace.github_operations.pr_manager
```

The contract keeps `name`, `type` and `layers` unchanged.

**Both edits must land in the same commit.** `unmatched_ignore_imports_alerting` defaults to
`error`, so once the flag removes those edges from the graph, a surviving waiver fails the
contract. Doing either half alone breaks `lint-imports`.

Leave every other contract's `ignore_imports` alone — the `pygithub`, `requests`,
`mcp_library`, `gitpython` and `subprocess_ban` waivers all cover real runtime imports.

## Why this is safe

Both waived imports sit inside `if TYPE_CHECKING:` in
`src/mcp_workspace/git_operations/base_branch.py` and exist only to annotate the
`IssueManager` / `PullRequestManager` parameters. `detect_base_branch` takes those managers as
injected optional arguments and skips the corresponding step when they are `None` — its
docstring says so explicitly ("avoids upward import from git_operations"). There is no runtime
upward dependency, so the waivers describe a violation that does not exist.

`importlinter.application.use_cases.create_report` reads `exclude_type_checking_imports` from
the `[importlinter]` session options and passes it to `grimp.build_graph`; the installed
version supports it.

## ALGORITHM

None — configuration only.

## DATA

None.

## Checks

`run_lint_imports_check` is the one that matters: it must pass with no waiver, proving the
flag took effect. Also run `run_tach_check` (unchanged behaviour expected) and the standard
`run_pylint_check` / `run_pytest_check` (`-n auto`) / `run_mypy_check` so the commit lands
green.

If `lint-imports` reports an unrecognised option, the installed import-linter predates the
flag — stop and report rather than restoring the waivers silently.

## LLM prompt

> Implement step 2 of issue #264. Read `pr_info/steps/summary.md` and
> `pr_info/steps/step_2.md`.
>
> Edit `.importlinter` only: add `exclude_type_checking_imports = True` to the `[importlinter]`
> session block with the trade-off comment from the step file, and delete the `ignore_imports`
> key and both `base_branch` entries from `[importlinter:contract:layered_architecture]`. Both
> edits go in one commit — a waiver whose edge no longer exists fails the contract, since
> `unmatched_ignore_imports_alerting` defaults to `error`. Do not touch `tach.toml`,
> `docs/ARCHITECTURE.md`, or any other contract's `ignore_imports`.
>
> Run `run_lint_imports_check` and `run_tach_check`, plus pylint, pytest (`-n auto`) and mypy.
> All must pass. Then stage and commit as
> `chore(importlinter): exclude TYPE_CHECKING imports, drop base_branch waivers`.
