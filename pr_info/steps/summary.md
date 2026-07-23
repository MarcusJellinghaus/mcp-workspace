# Summary — Issue #225: git tool UTF-8 mangling + broken search on `show <blob>`

## Problem

The read-only `git` tool (`mcp__mcp-workspace__git`, `git_operations/read_operations.py`)
has two **independent** defects, both reproduced on Windows against a real repo.

### Bug 1 — git output decoded as cp1252 instead of UTF-8
Every read function returns `repo.git.<cmd>(*args)` directly. GitPython hands back an
**already-decoded** `str`; on Windows that decode uses the OS locale code page (cp1252),
not UTF-8, so `e2 80 94` (em-dash `—`) becomes `â€"`. This is **not cosmetic**: it also
breaks the `search` parameter for any non-ASCII pattern, because the mojibake in the
output can no longer match the UTF-8 search pattern.

### Bug 2 — `search` returns "No matches" on `git show <blob>` (locale-independent)
`git_show` **always** routes `search` through `filter_diff_output()`. But when a colon
spec is used (`HEAD:file`), the output is **file content, not a diff**. The code already
detects this via `has_colon` (to skip compact rendering) yet still applies the
diff-structure filter → `parse_diff()` finds no `diff --git` hunks → "No matches"
regardless of content. Reproduces with pure ASCII, so it is unrelated to Bug 1.

## Architectural / Design Changes

1. **New single decode chokepoint — `run_git_text()` in `git_operations/core.py`.**
   Today there is **no** execution chokepoint: 12 `repo.git.*` read call sites each decode
   independently — exactly how this bug survived. We introduce one helper that forces
   UTF-8 decoding and route **all 12** read-only call sites through it. Decoding then
   happens in exactly one place, and the uniform path prevents the next mixed-encoding
   regression.
   - Contract: `getattr(repo.git, method)(*args, stdout_as_string=False)
     .decode("utf-8", errors="replace")`, then `.rstrip("\n")`.
   - `stdout_as_string=False` returns raw **bytes** we decode ourselves.
   - `errors="replace"` — this is a read-only display/search tool where robustness beats
     byte-fidelity; invalid bytes become `�` and never crash.
   - `.rstrip("\n")` restores GitPython string-mode behaviour (bytes mode keeps trailing
     newlines that string mode strips). Without it, the `if not output:` empty-checks
     ("No changes found" / "No output.") and exact-output tests break.
   - Exceptions (`GitCommandError` handling in `git_log` / `git_merge_base` /
     `git_check_ignore`) stay at the call sites — they now wrap the `run_git_text(...)`
     call. The helper only decodes.

2. **New content-aware search filter — `filter_content_output()` in
   `git_operations/output_filtering.py`.** A line-based grep sibling to
   `filter_diff_output` / `filter_log_output`: returns matching lines ± `context`.
   Case-insensitive (`re.IGNORECASE`) and reuses the identical sibling messages
   (`No matches for search pattern '{search}'`, `Invalid search pattern: {e}`) so there is
   one predictable search contract across all commands.

3. **`git_show` selects the filter by content type.** Reuse the already-computed
   `has_colon` flag: colon spec (content) → `filter_content_output`; real diff →
   `filter_diff_output`. The fix is localized to `git_show`; `git_diff` is untouched
   (its output is always a real diff).

### Design choices deliberately kept simple (KISS)
- **Full route-through, not surgical.** Even ASCII-only outputs (`rev_parse`,
  `merge_base` SHAs) go through the helper — decoding ASCII costs nothing and a uniform
  path is simpler than per-site judgment about which output needs UTF-8.
- **`filter_content_output` stays self-contained (~12 lines).** We do *not* extract a
  shared grep helper with `_filter_hunks`: the hunk version tracks hunk headers, the
  content version does not; a shared abstraction would couple two things that only look
  alike.
- **Rejected alternative:** making `filter_diff_output` fall back to line-grep when
  `parse_diff()` is empty. It would silently change that function's contract and could
  mask genuine "no diff structure" cases. A new, explicit helper selected by `has_colon`
  is the smaller, more honest change.
- **Test mocks return bytes, not a mocked `run_git_text`.** Routing through the helper
  (which calls `.decode()`) means existing mocks that stub `repo.git.<cmd>` with a `str`
  break. We update them to **`bytes`** rather than mocking the helper away — this keeps
  the new decode chokepoint under test.

## Testing strategy
- **Bug 1 (CI cannot reproduce naturally** — CI runs a UTF-8 locale, so real git decodes
  correctly there). The injected-bytes unit test on `run_git_text` is the real regression
  guard.
- **Bug 2 is locale-independent**, so a real-repo integration test for
  `show <blob> search=...` is a genuine guard, alongside `filter_content_output` unit
  tests.

## Files created / modified

### Created
- `pr_info/steps/summary.md` (this file)
- `pr_info/steps/step_1.md`, `pr_info/steps/step_2.md`

### Modified — source
| File | Change |
|------|--------|
| `src/mcp_workspace/git_operations/core.py` | Add `run_git_text(repo, method, *args)` |
| `src/mcp_workspace/git_operations/read_operations.py` | Route all 12 `repo.git.*` read call sites through `run_git_text`; import it |
| `src/mcp_workspace/git_operations/output_filtering.py` | Add `filter_content_output(text, search, context)` |

### Modified — tests
| File | Change |
|------|--------|
| `tests/git_operations/test_read_operations.py` | Switch broken `str` mocks → `bytes`; add injected-bytes unit guard for `run_git_text` |
| `tests/git_operations/test_output_filtering.py` | Add `filter_content_output` unit tests |
| `tests/git_operations/test_read_operations.py` (or a show-focused test) | Add real-repo integration test for `show HEAD:<file> search=...` |

## Step overview (one commit each)
- **Step 1 — Bug 1 (encoding chokepoint).** Add `run_git_text`, route all 12 call sites,
  sweep broken mocks to bytes, add the injected-bytes unit guard.
- **Step 2 — Bug 2 (content-aware search).** Add `filter_content_output` + unit tests,
  wire it into `git_show` via `has_colon`, add the real-repo integration guard.

Bug 1 and Bug 2 are independent, so they are separate commits. Within each step the parts
are tightly coupled (a helper plus its only call site / the mocks it breaks) and must land
together to keep checks green.
