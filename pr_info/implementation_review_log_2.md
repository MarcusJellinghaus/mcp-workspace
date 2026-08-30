# review-implementation review log 2

Issue #265 — `get_base_branch`: stale local `main` shadows `origin/main`.

Continues from [implementation_review_log_1.md](./implementation_review_log_1.md),
which ran three rounds and ended needing a rebase.

## Round 4 — 2026-08-30

**Findings**:

- **Critical** — `src/mcp_workspace/server.py:37-39`: CI's `isort` job is red on this
  branch. CI runs `isort --check --profile=black --float-to-top src tests`, which is not
  the invocation `run_format_code` uses, so the local format loop never normalised the
  single-name `set_reference_projects` import that this branch wrapped in parentheses.
- Low — `parent_branch_detection.py:106`: the default-branch early return is guarded by
  `default_branch is not None`, so in a repo with no `origin/HEAD` and no local
  `main`/`master` the guard is skipped and another branch is still returned as the base.
  The docstring documented this escape hatch only under the tie bullet.
- Low — `checks/branch_status.py:422`: `report_data.get("default_branch_name") or "main"`
  names a possibly non-existent `origin/main` in that same configuration.
- Low — `checks/branch_status.py:577`: `get_default_branch_name` is now called three times
  per `collect_branch_status` (also from `detect_base_branch` step 5 and `needs_rebase`),
  each shelling out to `git symbolic-ref`.
- Branch is 3 commits behind `origin/main`.

**Decisions**:

- **Accept** `server.py`. Rounds 1–3 dismissed this import as cosmetic scope drift; the new
  evidence is that it breaks CI, which changes the verdict. Reverting to the one-line form
  greens CI *and* removes the out-of-scope diff.
- **Accept** the `parent_branch_detection.py` docstring note. One sentence, documents real
  behaviour the docstring previously misstated.
- **Skip** `branch_status.py:422`. Same unresolvable-default configuration; there is no
  better name to fall back to, so the change would trade one guess for another.
- **Skip** `branch_status.py:577`. Performance micro-optimization outside issue #265's
  scope, and rated not worth doing on its own by the reviewer.
- **Defer** the rebase to the branch-status step.

**Changes**:

- `src/mcp_workspace/server.py` — reverted the `set_reference_projects` import to the
  single-line form on `origin/main`. The file now has zero diff against `origin/main`.
- `src/mcp_workspace/git_operations/parent_branch_detection.py` — extended the
  default-branch bullet in the `detect_parent_branch_via_merge_base` `Returns:` block to
  state that the check is skipped when no default branch resolves. Docstring only.

Checks: pylint clean, mypy clean, 1715 unit tests passed (1 skipped), 367 git-integration
tests passed (1 skipped), `run_format_code` clean.

**Status**: committed as `b6cd0d6`. CI went green on that commit — all 13 jobs, including
the previously-failing `isort`.

## Round 5 — 2026-08-30

**Findings**:

- No logic defects, no critical issues.
- Low — `tests/checks/test_branch_status_recommendations.py`: nothing pinned the
  `default_branch_name` interpolation added in round 2. Every recommendation case either
  passed `"main"` or omitted the key and relied on the `or "main"` fallback, and the
  end-to-end case mocked the default branch to `"main"` too, so a regression back to a
  hardcoded `Rebase onto origin/main` / `Pull origin/main` would have left the whole suite
  green.

**Decisions**:

- **Accept**. A real coverage gap on behaviour introduced by this review, closable with two
  bounded test cases.

**Changes**:

- `tests/checks/test_branch_status_recommendations.py` — added
  `test_rebase_uses_non_main_default_branch_name` and
  `test_pull_uses_non_main_default_branch_name`, both using
  `"default_branch_name": "master"` and pinning one arm of the ternary each. Verified they
  bite by temporarily hardcoding the f-string back to `origin/main`: exactly the two new
  tests failed, nothing else. No source changes.

Checks: pylint clean, mypy clean, 1717 unit tests passed (1 skipped), 367 git-integration
tests passed (1 skipped), `run_format_code` clean, all files within the 750-line limit.

**Status**: committed as `ee47461`.

## Round 6 — 2026-08-30

**Findings**: none. Confirmation round over `ee47461`.

The two new tests were verified mutation-sensitive against the f-string at
`checks/branch_status.py:452-454`, match the file's existing idiom, and cover both the
`Rebase onto` and `Pull` arms. No production code changed since round 5; `server.py`
remains absent from the diff against `origin/main`.

**Decisions**: nothing to accept or skip.

**Changes**: none.

**Status**: clean round — review loop ends.

## Final Status

**Review complete after three rounds in this run (rounds 4–6), following three in
[log 1](./implementation_review_log_1.md).** Round 6 produced zero findings.

All five planned changes for issue #265 are implemented and covered:

1. `parent_branch_detection.py` — local/remote dedupe dropped; every ref scored in one loop
   with a sha-keyed distance cache.
2. `parent_branch_detection.py` — returns `None` on the default branch.
3. `parent_branch_detection.py` — minimum distance per branch name, explicit tie rule,
   `None` on an unresolved tie between distinct non-default names.
4. `workflows.py` — `current_branch == target_branch` short-circuit removed, with
   `up-to-date` preserved for a never-pushed current branch.
5. `checks/branch_status.py` — `is_default_branch` and `default_branch_name` plumbed into
   `report_data`; `Pull origin/<default>` on the default branch, `Rebase onto
   origin/<default>` elsewhere.

**Quality gates**: pylint clean, mypy clean, 1717 unit tests passed (1 skipped), 367
git-integration tests passed (1 skipped), `run_format_code` clean, vulture clean,
lint-imports 9 contracts kept / 0 broken, all files within the 750-line limit.

**CI**: green on `b6cd0d6` (13/13 jobs). The `ee47461` run postdates that check.

**Deliberately out of scope** (recorded so they are not re-raised):

- No `fetch` before detection — a never-fetched `origin/main` is still scored stale. Per the
  issue: the alternative puts network I/O into a path that has none.
- `checks/branch_status.py` `or "main"` fallback when no default branch resolves — no better
  name to fall back to.
- `get_default_branch_name` called three times per `collect_branch_status` — out-of-scope
  performance work.
- In a repo with no `origin/HEAD` and no local `main`/`master`, detection on the trunk still
  returns another branch. Now documented in the `Returns:` block rather than fixed.

**Open before merge** (outside this review):

- Branch is 3 commits behind `origin/main` and needs a rebase. Path analysis says it should
  apply cleanly: upstream touches only `.claude/settings.local.json`, one skill file and
  `pyproject.toml`, none of which this branch's 14 commits touch. An earlier unclean attempt
  predates `b6cd0d6` and does not reproduce from the current state.
- CI's `check-forbidden-folders` job runs only on pull requests and blocks any PR containing
  `pr_info/steps`. It was skipped on every push-triggered run here, so it has never been
  exercised. `pr_info/` must be cleaned up before the PR is opened — normally handled by the
  PR-creation stage.
