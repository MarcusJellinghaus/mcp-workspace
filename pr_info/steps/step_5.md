# Step 5 — Document the two newly rejected input classes in README.md

Read [summary.md](./summary.md) first. Depends on step 1. Docs-only commit.

Step 1 narrows the set of accepted paths in two user-visible ways, and neither is currently
stated anywhere a user reads. The issue asks for the symlink rejection to be stated rather
than discovered; the mid-path `..` rejection is the same kind of change. This repo has no
`CHANGELOG.md` and release logistics sit outside this issue, so `README.md` — which already
claims "All operations are securely contained within your specified project directory"
(`README.md:18`) and carries a reference-project **Security Notes** list (`README.md:147-152`)
— is the user-visible surface.

## WHERE

| File | Change |
|---|---|
| `README.md` | New `## Path Confinement` section; one cross-reference bullet in **Security Notes** |

No source file and no test is touched.

## WHAT

A new top-level section placed immediately after the `## Overview` section (before
`## Features`), so it sits next to the containment claim at `README.md:18` that it qualifies.

## HOW

- State the rule once, then the two rejected input classes with a concrete example each.
- Say what a user does instead, for both — otherwise the section reports a loss without a
  remedy. For content outside the project, that is `--reference-project` (read-only) or a
  second server instance; for `..`, it is writing the path without the segment.
- Cover reference projects explicitly: they pass their own directory in as the project
  directory and inherit the same rule, so a reader configuring `--reference-project` needs to
  know the same two rejections apply there.
- Add one bullet to the existing reference-project **Security Notes** list pointing at the new
  section, rather than repeating the rules there.
- Do not restate the CVE, the advisories or the reporter credits — the issue's Decisions table
  puts advisory and release logistics outside this change.

## DATA

Section content (wording may be adapted; the two rejections and both remedies must survive):

```markdown
## Path Confinement

Every path is validated against the project directory before any file operation. Validation
resolves the path — following `..` segments and symlinks — and rejects it if the result lies
outside the project directory. Reference projects are validated the same way against their
own directory.

Two kinds of path are rejected that earlier versions accepted:

- **A `..` segment anywhere in the path**, not only a leading one. `read_file("src/../README.md")`
  is rejected; use `read_file("README.md")`.
- **A path that leaves the project through a symlink.** A symlinked file inside the project
  whose target is outside it, or an intermediate symlinked directory component, is rejected
  even though the path contains no `..`. To read content that lives outside the project,
  configure it with `--reference-project` (read-only) or run a second server instance
  pointed at it.
```

## Checks

`run_format_code`, then `run_pylint_check`, `run_pytest_check` (`extra_args: ["-n", "auto"]`),
`run_mypy_check`. Nothing here changes Python, but `tests/test_reference_projects_mcp_tools.py`
asserts on README content (`test_readme_usage_example_matches_source`), so the suite still has
to run.

## Commit

`docs(readme): state the two paths the guard now rejects (#290)`

## LLM prompt

> Implement step 5 of the plan in `pr_info/steps/step_5.md`, using `pr_info/steps/summary.md`
> for context. Steps 1–4 must already be committed.
>
> This is a docs-only commit: add the `## Path Confinement` section to `README.md` after
> `## Overview`, per the DATA section, and add one bullet to the reference-project **Security
> Notes** list (`README.md:147-152`) pointing at it. Both rejected input classes and both
> remedies must appear. Change no source file and no test.
>
> Then run `run_format_code`, `run_pylint_check`, `run_pytest_check` with
> `extra_args: ["-n", "auto"]`, and `run_mypy_check`. One commit for the step.
