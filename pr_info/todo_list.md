# Security & code quality: bring mcp-workspace in line with mcp_coder

Propagation of epic [mcp_coder#1163](https://github.com/MarcusJellinghaus/mcp_coder/issues/1163).
Target config: `mcp_coder/pyproject.toml` and `.github/workflows/ci.yml`.

Counts measured on `main` @ `5359a44` (2026-11-05) over `src tests tools`, with the
preview gate from task 1 applied. The gate removed `UP052` (11) and `S404` (8).

## Decisions

- Follow mcp_coder as closely as possible. Deviate only where the epic says to or the repo differs, and record the reason.
- One PR, one commit per task or chore section. Branch `chore/align-quality-with-mcp-coder`.
- PR says `Part of #72`, never `Closes` (chore issues are long-lived).
- This file is deleted before the PR, because task 28 blocks `pr_info/` in CI.

## Chores from #72

Per section: verify still needed, verify against the source, apply, commit, push, tick the boxes in #72.

- [x] **C1. Remove pycycle.** Already gone from mcp_coder. `R0401` stays enabled here.
- [x] **C2. Disable the setup-uv cache.** `ci.yml` (4 steps) and `upstream-mypy-check.yml` (1 step). mcp_coder hasn't applied this yet, so this is a deliberate lead over it.
- [x] **C3. Remove `--venv-path` from `.mcp.json`.** mcp_coder still has it; the chore is independent of that.
- [x] **C4. Re-sync GitHub labels.** Done on GitHub, no repo change: 17 created, 21 updated, 0 deleted.
- Skipped: **remove the sleep from `issue_analyse`.** Still blocked, mcp_coder's own copy still has it.

## Tasks, in order

### Ruff rules

- [x] **1. Gate preview rules (#1164).** Per-rule counts identical before and after (1349 across 16 rules, `--ignore-noqa`, per-file-ignores cleared). Clearing the `DOC502` per-file-ignores makes 18 findings fire, so `DOC` is still enforced.
- [x] **2. Pin ruff.** `ruff>=0.9.0` becomes `ruff~=0.17.2` in the `dev` extra (#1296).
- [x] **3. Add `tools` to the ruff scope; align `D`/`DOC`.** Rename CI row `ruff-docstrings` to `ruff`, running `ruff check src tests tools`. Drop the `D104` ignore (3 hits in `src`). Fix `D` in `tools` (10). Add `"tools/**" = ["DOC201"]` (10 hits); fix `DOC402` (1).
- [x] **4. `C4` + `B` (#1165): 8 findings.** Set `zip(strict=)` per call site, not as a blanket value.
- [x] **5. `E`, ignore `E501` (#1167): 47 findings.** All `E712`, all in tests. `E501` (217 hits) stays off permanently.
- [x] **6. `SIM`, with `SIM117` ignored in tests (#1168): 16 findings to fix.** The 78 `SIM117` hits are all in tests, so the carve-out covers them.
- [x] **7. `F` (#1169): 139 findings, all in tests/tools.** `F401` 120, `F811` 11, `F841` 8. Keep imports that are the test's actual content, and assert on them. Must land before task 10.
- [x] **8. `ANN`, ignore `ANN401` (#1171): 0 findings to fix.** All 136 hits are `ANN401`. Config change only.
- [x] **9. `S` with filters (#1170): 30 findings after filtering (6274 raw).** Test-only ignores: `S101`, `S105`, `S106`, `S108`. Do **not** copy mcp_coder's global `S404`/`S603` ignores, as the epic says: `S404` has 0 hits once gated and `S603` has 0 in `src`, so scope any `S603` ignore to tests/tools. Review `S101` (10), `S105` (1), `S110` (2) and `S311` (1) in `src`.
- [x] **10. `UP` (#1166): 1181 findings, own commit.** `run_ruff_fix(select=["UP", "F401"])`, then `UP042` separately with `--unsafe-fixes` (5 sites in `src`). `StrEnum` changes `str()` and f-string output, so check each use. Re-measured 1175. No `src` site formats a member, all go through `.value`. `Dict[str, Any]` → `dict[str, Any]` on `search_files`, `search_reference_files` and `get_reference_projects` drops the `{"result": ...}` wrapper from their `structuredContent` and `outputSchema` (FastMCP only wraps non-`GenericAlias` dicts); text content is unchanged.
- [x] **11. `PLW1510` (3 findings) and `PLE2502` (0 findings) (#1177).** Cherry-pick the exact codes, not the `PL` group. `tools/tach_docs.py` uses `check=True`, deviating from mcp_coder's `check=False`: nothing inspects the exit code, and a failed `tach` otherwise writes blank docs and reports success.

### Formatter

- [x] **12. Migrate to ruff format and `I` in one PR (#1175).** Do this after the rule groups, so the reformat runs once on final code. `formatter = "ruff"`, empty `[tool.ruff.format]`, add `I` (3 hits), remove `[tool.black]`, `[tool.isort]` and both dev dependencies. CI: delete `black` and `isort` rows, add `ruff-format` over `src tests tools`. Delete `tools/black.bat`, `iSort.bat`, `format_all.bat`, `format_all.sh`. Update `tools/check_version.bat`, `run_all_checks.*`, `.gitignore` (`*.isorted`), `CONTRIBUTING.md`, `docs/ARCHITECTURE.md`, `.claude/CLAUDE.md`, and the `commit_push` and `implement_direct` skills.
- [ ] **13. Update required status checks in the same step as task 12 (manual).** GitHub matches them by job name, so a removed required name blocks every PR. Also covers the task 3 rename and the task 14/15 job changes. Keep required checks in the ruleset only, not also in classic protection.

### Dependencies and coverage

- [x] **14. deptry (#1176, #1290): 22 findings.** Add `[tool.deptry]` with `optional_dependencies_dev_groups` (clears the 17 `DEP002`). Declare `requests` and `typing_extensions` in `[project.dependencies]` (the 5 `DEP003`). Add `tools/deptry_check.sh/.bat` and a CI row. Re-measured 18 after task 10: 14 `DEP002`, 4 `DEP003` (`requests`). `typing_extensions` is not declared: `UP035` removed its `src` use, and the last import was a dead `except ImportError` branch in `tests/conftest.py`, now deleted. New required-check candidate: `deptry`.
- [x] **15. Coverage reporting, never a gate (#1178).** Split `unit-tests` and `git-integration-tests` out of the `test` matrix into their own jobs, then add a combining `coverage` job with `diff-cover`, `pytest-cov`, `tools/ci_coverage_summary.py` and `.gitignore` entries. `github-integration-tests` is skipped without secrets, so the job's `needs:` must not let that skip the coverage job. Local total 92.49% (unit + git + github, 9182 statements). `top_level_package_name` strips `src.mcp_workspace`: after `coverage combine` the XML names packages from the working directory, so mcp_coder's copy would bucket everything under `src`. New required-check candidate: `coverage`.

### Security

- [x] **16. Gate `/approve` on commenter trust (#1310).** Real hole: `approve-command.yml:10` has no `author_association` check, so any GitHub user can promote an issue. Top priority in this section. Regenerate with mcp-coder's generator, which also adds top-level `permissions: {}` to both generated workflows. Don't hand-edit. Regenerated with `write_github_actions()` (no label sync), byte-identical to the generator. The generator also SHA-pins `github-script`, so task 18 only has the other workflows left.
- [x] **17. Add `SECURITY.md` (#1310).** Missing here. Adapt mcp_coder's scope and threat model.
- [x] **18. SHA-pin all GitHub Actions (#1310).** With a `# vX.Y.Z` comment, so Dependabot keeps them updated. Includes `pypa/gh-action-pypi-publish@release/v1` in `publish.yml`.
- [x] **19. Signed release assets (#1310).** Add the `attach-signed-artifacts` job to `publish.yml`.
- [ ] **20. Enable CodeQL default setup (manual; #1163 follow-up 4).** Needed before the CodeQL badge can render.
- [ ] **21. Add `.github/workflows/scorecard.yml` (#1291).** Publish results and upload SARIF. Not a required check. Triage the resulting code-scanning alerts once after merge.

### Badges

- [ ] **22. License metadata (#1291).** `LICENSE` already exists. Set `license = "MIT"` and `license-files = ["LICENSE"]`, raise to `setuptools>=77`, and remove the `License ::` classifier (the build fails if it stays).
- [ ] **23. Coverage badge plumbing (#1291).** Needs task 15. Reuse the shared gist with file `mcp-workspace-coverage.json`, because an unrenamed copy overwrites mcp_coder's badge. Manual: set secret `BADGE_GIST_TOKEN` and variable `BADGE_GIST_ID`.
- [ ] **24. Add the README badges (#1291).** Under the title. Metadata: CI, PyPI, Python, License. Quality: Ruff, mypy strict, pylint, architecture, coverage. Security: Scorecard, CodeQL. Only list tools that actually run here.
- [ ] **25. Verify after merge.** Every badge renders, coverage shows a percentage (not `pending`), Scorecard published.

## Also needed (not sub-issues of the epic)

- [ ] **26. Enable pylint `W`.** Use mcp_coder's `disable` list (`C`, `R` and 10 named `W` codes). Not measured yet.
- [ ] **27. Align the `ci.yml` layout.** `push-checks` / `pr-checks` split, dependency install via `tools/read_github_deps.py`, comment header explaining which job runs when. Update required checks with task 13.
- [ ] **28. Align `check-forbidden-folders`.** mcp_coder blocks all of `pr_info/`; here only `pr_info/steps`, `pr_info/.conversations` and `.commit_message.txt` are blocked.
- [ ] **29. Update the epic and wiki when done.** Comment on #1163. Add any lessons to the wiki as a Field Note. mcp-tools-py is still on the old ruff block, so track its propagation in its chore issue (mcp-tools-py#107).
- [x] **30. Fix drift in `tools/` scripts.** `run_all_checks.*` now runs every CI row that has a wrapper (9 steps, adds ruff lint, vulture, deptry) and calls `mypy.bat`, not the missing `mypy_check.bat`. `ruff_check.*` covers `tools`. Removed `update_packages.bat`, whose `requirements.txt` no longer exists. Fixed `CONTRIBUTING.md` and `docs/ARCHITECTURE.md`.

## Not applicable here

| Issue | Why |
|---|---|
| #1172 `TRY400` | Rejected upstream |
| #1173 | mcp_coder's own formatting wrapper |
| #1179, #1180 | `mcp-coder verify` changes (upstream part already in this repo) |
| #1181, #1307 | #1181 is explicitly mcp_coder only; #1307 only collects questions |
| #1311 | Coordinator change; its dependency here (`check_body_trust`) already landed |
