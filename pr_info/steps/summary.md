# Summary — Issue #288: bound `check_file_size` report output

## Problem

`check_file_size` renders an unbounded report. A live run on 2026-09-03 against a project with
vendored dependency trees returned **118.3 KB / 855 lines** listing **845 violations** in a single
tool response; the calling harness elided the middle inline and preserved it only in an
out-of-band artifact.

`render_output` (`src/mcp_workspace/checks/file_sizes.py:145-181`) has **two** unbounded loops —
violations (line 165) and stale allowlist entries (line 178). `server.py:1553` returns the string
unmodified, so any bounding must happen inside `render_output`.

## Solution

Fixed internal caps of 50 on both enumerations, with a truncation notice. **No new tool
parameter.** This is the "internal caps: improve the message, document the cap" category from
#257 — not the liftable-parameter category.

## Architectural / design changes

**None structurally.** No new module, no new class, no signature change, no new dependency, no
change to the MCP tool's parameter list. The change is two slices and two conditional lines inside
one existing rendering function, plus two module-level constants.

Design decisions worth recording:

| Decision | Rationale |
|---|---|
| **Cap inside `render_output`, not at the `server.py` boundary** | The boundary sees an opaque string; truncating there would cut mid-line and lose the remedy sentence. |
| **Two separate constants, not one shared `_MAX_ITEMS = 50`** | The two caps bound unrelated things and may diverge; each carries its own justification comment. Required by the issue. |
| **No lift parameter — violations 51+ are unreachable from the tool** | Accepted deliberately. A `max_report_violations=845` hint would only reproduce the 118 KB payload the harness elides. `max_lines` is the *threshold*, not a report bound — it is not overloaded. |
| **No shared truncation helper** | The two sites differ in item formatting and notice text, so a helper needs a formatter callable — more moving parts than the four lines it saves. Deliberately not DRY-ed. |
| **Notice must not name a parameter** | Per #257, internal-cap sites document the cap in a code comment and do not invent a lift. |
| **`render_output`'s signature is unchanged** | `tests/test_server_file_size.py:44-69` mocks it and asserts `call_args.args[1]`. Zero test churn there. |
| **`render_allowlist` (`file_sizes.py:184`) stays unwired** | It has no production caller in this repo. It is not a workaround for the cap and gets no `format="allowlist"` parameter. |
| **`mcp_coder`'s near-duplicate `checks/file_sizes.py` is NOT changed** | Its consumer is a terminal CLI where full output is legitimate. Do not propagate this cap there. The twin has already diverged four ways (no stale sort, different pass-path summary, stale entries rendered only on the pass path, no allowlisted-count line on the fail path), so a later sync is not a straight copy in either direction. |

### Ordering determines the notice wording

- **Violations** are sorted by line count descending (`file_sizes.py:134`), so the head is the
  worst offenders and truncation drops only the least severe tail. The notice therefore claims an
  ordering: `(largest first)`.
- **Stale entries** are sorted alphabetically (`file_sizes.py:127`), so the head is an arbitrary
  slice and only the count is severity-bearing. The notice makes **no ordering claim**.

### Documented, not fixed

Three true statements about scan scope get written down rather than changed:

1. **Nested `.gitignore` files are never read.** `filter_with_gitignore`
   (`directory_utils.py:166`) receives a single `base_dir` path, so a tree excluded by
   `vendor/.gitignore` is still scanned and reported — a plausible contributor to the observed
   845. Changing this would alter what `search_files`, `list_directory` and `delete_directory`
   see.
2. **`list_directory` applies the *listed* directory's `.gitignore`, not the project root's.**
   `list_files` passes the listed directory as `base_dir` (`directory_utils.py:216` → `:166`), so
   `list_directory(path="src")` reads `src/.gitignore`. `README.md:243` currently states this
   wrongly.
3. **The allowlist is not the narrowing path for the reported trigger.** `load_allowlist` builds
   exact normalized path strings and matching is `normalized in allowlist` (`file_sizes.py:119`) —
   no globs, no directory prefixes. `vendor/`, `vendor/**` and `node_modules/*.js` all match
   nothing; silencing 845 vendored files would need 845 lines. The remedy for that scenario is
   `.gitignore`. The allowlist works as designed for its actual audience (this repo's own
   7-entry `.large-files-allowlist`), so the report's closing remedy sentence **stays unchanged**.

No follow-up issues are filed for any of the three.

## Non-blocking observation

The stale-entries cap fires on a set of paths a human typed into `.large-files-allowlist`.
Reaching 312 stale entries requires a 312-line allowlist, which the issue itself argues is not the
working mode. The cap is cheap and symmetric so it is implemented as specified — but the
violations cap is the one that will actually fire in practice.

## Files created / modified

| Path | Change |
|---|---|
| `src/mcp_workspace/checks/file_sizes.py` | **Modified** — two module-level constants with cap comments; two slices and two conditional notices inside `render_output`. ~12-line diff. |
| `tests/checks/test_file_sizes.py` | **Modified** — one module-level fixture builder plus four cases added to the existing `TestRenderOutput` class. |
| `src/mcp_workspace/server.py` | **Modified** — one scan-scope paragraph added to `check_file_size`'s docstring. First line unchanged. |
| `README.md` | **Modified** — `#### List Directory` bullet split and corrected; `check_file_size` tool-table row added; `#### Check File Size` Tool Details block added. |
| `docs/processes-prompts/refactoring-guide.md` | **Modified** — line 104's wrong scan-scope sentence corrected. |

No files or folders are created. No module is added, moved, renamed or deleted.

**Explicitly untouched:** `tests/test_server_file_size.py` (mocks `render_output`; unaffected by an
unchanged signature), the single-violation cases at `tests/checks/test_file_sizes.py:131-160`,
`render_allowlist`, and `mcp_coder`'s twin implementation.

## Steps

| Step | Scope | Commit |
|---|---|---|
| [step_1](step_1.md) | The two caps + tests | `feat(file_sizes): cap violation and stale-entry reports at 50` |
| [step_2](step_2.md) | `check_file_size` docstring scan scope | `docs(server): state check_file_size scan scope` |
| [step_3](step_3.md) | README — List Directory correction + `check_file_size` entry | `docs(readme): document check_file_size and fix gitignore scope` |
| [step_4](step_4.md) | `refactoring-guide.md:104` correction | `docs(refactoring-guide): correct file-size check scope` |

Steps 2-4 are documentation-only. Step 3 must run **after** step 1: its README block documents the
two 50-item caps, so committing it first would describe behaviour the code does not yet have.
Steps 2 and 4 are independent of everything else and can be done at any point. Each step is a
separate commit per the one-commit-per-step rule.

## Acceptance criteria coverage

**Tested** (step 1)

- Violations capped at 50 with `... showing 50 of {total} violations (largest first)`.
- Stale entries capped at 50 with `... showing 50 of {total} stale entries`.
- Both caps are named constants.
- Summary line, allowlist count and remedy sentence unchanged, including when both caps fire.
- Cases: >50 violations, >50 stale entries, both at once, exactly 50 (no notice).

**Verified in review**

- Each cap constant carries a deliberate-cap comment (step 1).
- Neither notice names a tool parameter (step 1).
- `render_output`'s signature is unchanged (step 1).
- Docstring first line unchanged, scope in a body paragraph before `Args:` (step 2).
- README List Directory bullet states the listed-directory `.gitignore` behaviour (step 3).
- README has a `check_file_size` table row and a Tool Details block carrying the scan scope (step 3).
- `refactoring-guide.md:104` no longer says "tracked Python files" (step 4).

## References

- #257 / PR #262 — house style for bounded output; this is the internal-cap category.
- #130 / PR #136 — `search_files` budget precedent. Its **char** budget is deliberately not
  copied: match context blocks vary wildly in size, violation lines do not, so a plain count is
  more predictable here.
- #235 — salience pattern behind the terse docstring first line.
- #221 / PR #223 — default limit resolution (`max_lines` → `--file-size-limit` → 600).
- PR #121 — the allowlist.
