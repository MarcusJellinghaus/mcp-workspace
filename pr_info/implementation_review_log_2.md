# review-implementation review log 2

Issue #252 — Advertise reference-project capability via server instructions.

Continues from `implementation_review_log_1.md`, which ended after round 3 with a
dismiss verdict and a rebase escalation.

## Round 1 — 2026-09-01

**Findings**:
- `src/mcp_workspace/server.py:49-51` — medium — the always-on instructions claim
  unconditionally that a reference project is a local checkout with readable files and
  git history, but `src/mcp_workspace/main.py:147` accepts a URL-configured project
  whose path does not exist. The GitHub half of the same sentence was already qualified
  in log 1 round 2; the file/git half was not.
- `README.md:213-237` — low — the per-tool table omits `get_base_branch`,
  `check_file_size` and `check_branch_status`.
- `src/mcp_workspace/server.py:53-55` — low — ragged wrapping in the instructions
  literal, left by the round-2 splice; black does not reflow concatenated strings.
- `src/mcp_workspace/server.py:49-57` — low — the text is ~76 words against the plan's
  ~60-70 target.

All six issue verification criteria met. pytest 2274 passed / 2 skipped, pylint, mypy
and ruff `D`/`DOC` clean.

**Decisions**:
- **Accept** the medium finding. Text that ships in every session should not be
  hedged in one direction only.
- **Accept, folded into the same fix** — the ragged wrapping and the word count. The
  fix touches that literal anyway, so re-flow and trim rather than stacking a second
  hedge.
- **Skip** the `README.md` table finding. Those three tools were never part of this
  diff and their absence predates it; the issue states per-tool tables "stay as they
  are". Step 3 added rows only for tools whose other README mentions it removed.
  Pre-existing, out of scope.
- Log-1 round-3 findings were not re-raised; no new evidence surfaced for them.

**Changes**:
The premise behind the accepted finding turned out to be narrower than the review
stated, and verifying it changed the fix. A URL-only project has no directory at
startup, but that does not make files or git unavailable: every file, search and git
tool resolves through `get_reference_project_path()`, which awaits `ensure_available()`
and clones on first use. `ensure_available` raises only when the directory is missing
*and* no URL is configured — a combination startup validation already rejects. So the
conditional half is only the GitHub half, which was already hedged correctly.

The false claim was narrower: "full local checkouts ... configured when this server
starts" asserts a checkout a URL-only project does not have at startup. That assertion
was dropped rather than a second, incorrect hedge added. The GitHub condition moved
into its own sentence with the subject up front. Literal re-flowed to even widths;
76 words down to 67.

`src/mcp_workspace/server.py` only. `tests/test_server_instructions.py` unchanged —
all three assertions still hold and none encoded the claim that changed.

**Status**: committed

## Round 2 — 2026-09-01

**Findings**:
Two accuracy nits, both in the instructions literal at
`src/mcp_workspace/server.py:49-52`. No critical or high findings.

- low — GitHub access is described as belonging to "projects configured with a
  repository URL", but the URL is auto-detected from the local git remote, so the
  capability is not opt-in the way the text implies.
- low — `git()` is claimed unconditionally, but a reference project need not be a git
  repository; a plain directory is accepted.

All six issue verification criteria hold. pytest 2274 passed / 2 skipped, pylint, mypy
and ruff `D`/`DOC` clean. Branch status: CI passed, no rebase needed, 9/9 tasks
complete.

**Decisions**:
- **Accept both.** This text exists to tell agents what they can reach; understating
  it reproduces the under-use failure the issue targets. Accepted with the constraint
  that the fix must not stack hedges or exceed 70 words — an over-qualified block
  reads as "capability unavailable", which is worse than the imprecision.

**Changes**:
Verified against the code first. `detect_and_verify_url`
(`src/mcp_workspace/reference_projects.py:99`) returns the remote URL for any sibling
git checkout with no `url=` in the config, so GitHub access is indeed auto-detected.
Startup validation (`src/mcp_workspace/main.py:132-199`) has no `is_git_repository`
gate, so a plain directory is a valid reference project and `git()` would fail against
it.

The two conditions collapse: being a local checkout of a GitHub repository is what
supplies both the git history and the GitHub URL, so one leading qualifier covers both
causally instead of two independent hedges. File reading and searching stay
unqualified — they resolve through `ensure_available()`, which clones a URL-only
project on first use, as established in round 1.

"repositories" became "codebases" so the noun itself no longer asserts git. Still 67
words. `src/mcp_workspace/server.py` only; `tests/test_server_instructions.py`
unchanged and still passing — no assertion encoded either changed claim.

**Status**: committed

## Round 3 — 2026-09-01

**Findings**:
No critical or high findings. All six issue verification criteria met. pytest 2274
passed / 2 skipped, pylint, mypy and ruff `D`/`DOC` clean. CI passed, no rebase needed.

- `pr_info/steps/summary.md:81,103` — low — the testing note and file table place the
  instructions-content test in `tests/test_server.py`; it actually lives in
  `tests/test_server_instructions.py`.
- `README.md:382` — low, pre-existing — "a project with `url: null` cannot be used
  with `reference_name`" is over-broad; the URL gates only the GitHub tools.

The `instructions=` wording was re-checked claim by claim against the code and raised
nothing: no factual error, no tool name beyond the two exceptions, no project name, no
path, 67 words.

**Decisions**:
- **Skip** the `summary.md` staleness. `pr_info/` is scratch that is deleted at the end
  of the process; correcting a plan document nobody will read again is churn.
- **Accept** the `README.md` claim despite being pre-existing. Rounds 1 and 2 of this
  log spent two passes making exactly this distinction accurate in the always-on
  instructions text; shipping a README nine lines away that contradicts it would undo
  the point. One sentence, in a file this branch already edits.

**Changes**:
Verified first: `get_reference_repo_url`
(`src/mcp_workspace/server_reference_tools.py:119-120`) raises for a URL-less project,
and its only caller is `_issue_manager` (`src/mcp_workspace/server.py:813`), which
backs every GitHub tool taking `reference_name`. The reference file tools and `git()`
resolve through `get_reference_project_path` → `ensure_available`, which needs a URL
only when the directory is missing (`reference_projects.py:116-121`). So the URL gates
the GitHub tools and nothing else.

`README.md` line 382 now reads that a `url: null` project still works with the
reference file tools and `git()` but not the GitHub tools. The redundant "tells a
caller whether the project supports the GitHub tools" clause was dropped, since the
replacement says it directly. `README.md` only.

**Status**: committed

## Round 4 — 2026-09-01

**Findings**:
No critical or high findings. All six issue verification criteria met. pylint, mypy and
ruff clean; CI passed, no rebase needed, 9/9 tasks complete.

- `README.md:382` — low — the line round 3 rewrote claims a `url: null` project "still
  works with the reference file tools and `git()`", but `git()` is not reliable for that
  population.

The `instructions=` literal was re-checked claim by claim for a fourth time: no factual
error, no disallowed tool name, no project name, no path, 67 words.

**Decisions**:
- **Accept.** This is an error round 3 introduced, not a pre-existing one, and it
  inverts the truth rather than merely blurring it. One clause.

**Changes**:
Verified first. Startup validation (`src/mcp_workspace/main.py:147-153`) drops any
project whose path is missing when no URL was given, so every registered `url: null`
project has a local directory. `detect_and_verify_url`
(`src/mcp_workspace/reference_projects.py:74-101`) then returns `None` in exactly two
cases: the directory is not a git repository, or its remote cannot be read. So
`url: null` selects precisely for the projects `git()` can fail against — the round-3
line had it backwards.

The file-tools half is sound: `ensure_available` returns at `if project.path.exists()`
(`reference_projects.py:117-118`) before the `url is None` check on line 119. The
GitHub half is sound: `get_reference_repo_url`
(`server_reference_tools.py:119-120`) raises when `url is None`.

The `git()` claim was dropped rather than hedged — a field description is not the place
for conditionals. `README.md` only.

**Status**: committed

**Note (not acted on)**: `tests/test_startup_performance.py::test_server_startup_under_two_seconds`
failed once under parallel load (median 2.269s against a 2.0s threshold) and passed 3/3
in isolation. A load-sensitive benchmark, unaffected by a README edit. Pre-existing
flake, out of scope for this issue.

## Round 5 — 2026-09-01

**Findings**: None meeting the bar. Clean round.

`README.md:382` was re-verified against the code independently of round 4's report and
holds on both halves. All six issue verification criteria met.

**Decisions**: No action.

**Changes**: None.

**Status**: no changes needed

---

## Final Status

Five rounds. Four produced changes, the fifth was clean.

**Commits produced by this review**

| Commit | Change |
|---|---|
| `347f964` | Dropped the "full local checkouts ... configured when this server starts" claim from the instructions text — URL-only projects clone lazily, so file and git access is not conditional on a startup checkout. 76 words to 67. |
| `9454060` | Tied git and GitHub access to the checkout case with one causal qualifier: the URL is auto-detected from the git remote, so GitHub access is not opt-in, and a plain directory is a valid reference project so `git()` cannot be claimed unconditionally. |
| `5ec5d67` | Scoped the `url: null` restriction in `README.md` to the GitHub tools. |
| `148529e` | Removed the `git()` claim from that same sentence — `url: null` selects precisely for the non-git directories `git()` fails against. |

Every round's fix was verified against the code before being written, and three of the
five rounds overturned the premise the review had reported. Rounds 3 and 4 are a pair:
round 3's fix introduced the error round 4 removed.

**Quality gates**

- pytest: 2276 collected, 2274 passed, 2 skipped, 0 failed
- pylint: clean
- mypy: clean
- ruff `D`/`DOC` under project config: clean
- vulture: no output
- lint-imports: 9 contracts kept, 0 broken

**Issue verification criteria**: all six automatable criteria met. The seventh — that a
client actually surfaces the instructions block — still requires an MCP server restart
and no unit test reaches it.

**Open items**: none blocking. One pre-existing flake noted and not acted on:
`tests/test_startup_performance.py::test_server_startup_under_two_seconds` is
load-sensitive under parallel execution and passed in the final run.
