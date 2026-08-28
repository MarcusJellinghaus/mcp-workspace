# Task Status Tracker

## Instructions for LLM

This tracks **Feature Implementation** consisting of multiple **Tasks**.

**Summary:** See [summary.md](./steps/summary.md) for implementation overview.

**How to update tasks:**
1. Change [ ] to [x] when implementation step is fully complete (code + checks pass)
2. Change [x] to [ ] if task needs to be reopened
3. Add brief notes in the linked detail files if needed
4. Keep it simple - just GitHub-style checkboxes

**Task format:**
- [x] = Task complete (code + all checks pass)
- [ ] = Task not complete
- Each task links to a detail file in steps/ folder

---

## Tasks

### Step 1: `formatters.truncate_output` — name the cap and `max_lines`

Details: [step_1.md](./steps/step_1.md)

- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 2: `output_filtering.truncate_output` — restyle to the house pattern

Details: [step_2.md](./steps/step_2.md)

- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared

### Step 3: `ci_log_parser` — one marker, one spelling, name `max_log_lines`

Details: [step_3.md](./steps/step_3.md)

- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared (message used directly in commit `e3620de`
      "fix(ci_log_parser): unify truncation marker and clamp caps";
      `pr_info/.commit_message.txt` could not be written because it is gitignored
      and the MCP workspace server refuses gitignored paths, and the step is
      already committed so the transient file is moot)

### Step 4: `github_issue_list` — make the silent truncation notice reachable

Details: [step_4.md](./steps/step_4.md)

- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared (recorded below; `pr_info/.commit_message.txt`
      could not be written because it is gitignored and the MCP workspace
      server refuses gitignored paths, as in step 3)

  ```
  Emit a truncation notice from github_issue_list by over-fetching one result

  format_issue_list guarded its notice with len(issues) > max_results, but its
  only production caller capped the list at max_results first, so the condition
  was never true and the tool truncated silently.

  github_issue_list now clamps max_results with max(0, max_results) and asks
  the manager for capped + 1 issues; the surplus item is what proves more
  results exist, since issue listing has no total count. The formatter still
  receives the capped value and renders "30+". Without the clamp a negative
  max_results rendered "... showing -1 of -1+ results" over an empty list.

  The notice follows the house style: it states the applied cap and names the
  parameters that lift or narrow it, without naming a query parameter that this
  tool does not accept.
  ```

### Step 5: `github_search` — emit a notice with the exact total from `totalCount`

Details: [step_5.md](./steps/step_5.md)

- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared (recorded below; `pr_info/.commit_message.txt`
      could not be written because it is gitignored and the MCP workspace
      server refuses gitignored paths, as in steps 3 and 4)

  ```
  Emit a truncation notice from github_search using the exact search totalCount

  format_search_results guarded its notice with len(items) > max_results, but
  github_search capped the collected list at max_results first, so the
  condition was never true and the tool truncated silently.

  Unlike issue listing, search can state an exact total: GitHub returns
  total_count in the first search page and PyGithub exposes it as
  PaginatedList.totalCount. The notice now renders "showing 30 of 412 results
  — raise max_results or refine your query", comparing the exact total against
  the number of lines actually built rather than against the capped input.

  The collection loop switches from enumerate plus an i >= max_results guard
  to islice(results, max(0, max_results)). The old guard pulled item
  max_results before breaking, which fetched a second search page only to
  discard it — at a default cap of 30 against a 30-per-page endpoint, that was
  an extra request on every default-sized search. islice stops without that
  pull, so totalCount really does cost nothing extra. The max(0, ...) clamp
  preserves the old behaviour for a negative max_results, which enumerate
  silently treated as "collect nothing" but islice rejects with ValueError.

  totalCount is read after the loop and only when items were collected: the
  property falls back to a separate per_page=1 request when no page was
  cached, which is exactly the zero-result and clamped-to-zero cases, where
  the "No results found." early return discards the value anyway.
  ```

### Step 6: `pr_feedback` — reorder sections, restyle notices, add a conditional footer

Details: [step_6.md](./steps/step_6.md)

- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared (recorded below; `pr_info/.commit_message.txt`
      could not be written because it is gitignored and the MCP workspace
      server refuses gitignored paths, as in steps 3, 4 and 5)

  ```
  Reorder PR feedback sections and make the truncation footer conditional

  Conversation comments rendered second, ahead of changes-requested and alerts,
  but they never drain: nothing removes them as a PR progresses. Under the
  single 20-item cap a PR with 25 comments filled the budget with threads plus
  comments and alerts never rendered at all. The comments loop now runs last,
  behind the two sections that carry the merge verdict.

  This changes rendered text only. blocks_merge is computed from the feedback
  data, not from the rendered block, so a truncated display never turned a
  blocked PR into a clean one — what was lost was the detail of why.

  No per-section budgets: the shared cap stays, so more than 20 unresolved
  threads still starves alerts. That case is accepted; the fix targets the
  non-draining section, which is the one that occurs in practice.

  Both truncation notices adopt the house "showing X of Y" style. The per-body
  marker becomes "... (truncated: showing 10 of 20 lines)" and the item cap
  becomes "... and 10 more of 30 items — full list via
  github_pr_view(include_comments=True)". A new _FULL_TEXT_HINT footer renders
  as the last line, but only when a body was actually cut or the cap fired.

  Both mentions of github_pr_view are deliberate: the cap line offers the full
  list of items, the footer offers the full text of a body that was cut.
  include_comments=True is spelled out because it defaults to False on
  github_pr_view, unlike github_issue_view, so without it the reader lands on
  an empty result.

  _truncate_body keeps its signature and stays pure. The footer condition is
  computed by the caller, which compares the helper's output against its input
  at each of the three call sites — the helper returns its input unchanged when
  it does not cut. No tuple return, no marker sniffing, no threshold
  duplicated.

  Both constants gain the comment recording that they are deliberate internal
  caps with no lift parameter, naming github_pr_view(include_comments=True) as
  the alternative.
  ```

### Step 7: `tree_listing` — name the narrowing options in the truncation summary

Details: [step_7.md](./steps/step_7.md)

- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared (recorded below; `pr_info/.commit_message.txt`
      could not be written because it is gitignored and the MCP workspace
      server refuses gitignored paths, as in steps 3, 4, 5 and 6)

  ```
  Name the narrowing options in the tree listing truncation summary

  _truncate reported both numbers honestly — "... and 50 more entries
  (0 dirs, 50 files) — 300 total" — but named no way forward. list_directory
  has no max_lines-style lift parameter and is not getting one, so the summary
  now names the parameters that narrow the listing instead:
  "Narrow with path=<subdir> or dirs_only=True."

  A comment above the summary records that the 250-line cap is deliberate and
  names the alternatives, including search_files for targeted lookups.

  Message only: the signature, the length guard and the dir/file counting are
  untouched, and the file's — escape convention for the em dash is kept.
  This truncation is rare in practice — _collapse greedily collapses
  directories until the listing is under 250 lines, so _truncate only fires on
  a very wide, flat repo.
  ```

### Step 8: `file_tools` internal caps — state the cap in `search.py`, document both

Details: [step_8.md](./steps/step_8.md)

- [x] Implementation (tests + production code)
- [x] Quality checks: pylint, pytest, mypy — fix all issues
- [x] Commit message prepared (recorded below; `pr_info/.commit_message.txt`
      could not be written because it is gitignored and the MCP workspace
      server refuses gitignored paths, as in steps 3, 4, 5, 6 and 7)

  ```
  State the 500-char cap in the search_files marker and document both file_tools caps

  search_files capped each result line at _MAX_LINE_CHARS = 500 and reported
  "... [truncated, line has 1000 chars]" — the total in the slot where the cap
  belongs, so the reader learned how much was lost but not how much was kept.
  The marker now reads "... [line truncated: showing 500 of 1000 chars]",
  stating both numbers in the house "showing X of Y" order.

  Message only: the truncation condition, the slice, the surrounding character
  budget and the search_files result shape (mode, details, total_matches,
  truncated, matched_files) are all untouched. The existing multi-line string
  concatenation keeps its shape; only the f-string changes, and it now
  interpolates _MAX_LINE_CHARS rather than repeating 500 as a literal.

  Both remaining file_tools internal caps gain a comment recording that they
  are deliberate. _MAX_LINE_CHARS has no lift parameter and is not getting
  one: a single pathological line must not crowd out the rest of the results,
  and a caller who needs the whole line reads the file at the reported line
  number.

  _format_deleted_paths is left exactly as it stands, message included. That
  site is unlike every other truncation here — the deletion has already
  happened, so there is nothing for the reader to re-request, no cap to lift
  and no alternative to name, and the summary line already carries the true
  file and directory totals. Its comment exists so the next audit of
  truncation notices does not "fix" a correct message into the house style.
  ```

## Pull Request

- [ ] PR review
- [ ] PR summary
