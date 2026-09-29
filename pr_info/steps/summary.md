# Summary — Issue #294: sub-issue tools

Add three MCP tools that create, read and delete native GitHub sub-issue links
(the "epic + child issues" structure), closing the gap that currently forces a
raw `gh api` call:

| Tool | Writes? | Purpose |
|------|---------|---------|
| `github_subissue_add(parent_number, child_number, reference_name=None)` | yes | Link an existing issue as a sub-issue of another |
| `github_subissue_list(parent_number, max_results=30, reference_name=None)` | no | List an issue's sub-issues |
| `github_subissue_remove(parent_number, child_number, reference_name=None)` | yes | Unlink a sub-issue from its parent |

Same-repo only: one `reference_name` governs both numbers.

## Architectural / design changes

**One new mixin, composed into `IssueManager`.** `SubIssuesMixin` joins
`CommentsMixin`, `LabelsMixin` and `EventsMixin` on `IssueManager`
(`issues/manager.py:58`). No new manager, client, dependency or auth path.

**No GraphQL, no low-level requester calls.** PyGithub 2.10.0 (the version in
the project venv) types these endpoints directly — verified in the installed
library, not assumed:

- `Issue.add_sub_issue(sub_issue: int | Issue) -> SubIssue`
- `Issue.remove_sub_issue(sub_issue: int | Issue) -> SubIssue`
- `Issue.get_sub_issues() -> PaginatedList[SubIssue]`
- `SubIssue` is a subclass of `Issue`, defined in `github/Issue.py`
- `github.SubIssueSummary.SubIssueSummary` exposes int properties `completed`,
  `percent_completed`, `total`

Both write wrappers read `.id` off an `Issue` argument, so passing the child
**object** (never its number) removes the id-vs-number trap for free. The child
object is fetched anyway for the pull-request guard.

**Dependency floor rises to `PyGithub>=2.7.0`** (`pyproject.toml:30`, currently
`>=2.1.0`). 2.7.0 is the release that added sub-issues; without the bump the
code would be legal against the declared dependency and fail at runtime on
2.1–2.6. Unconstrained elsewhere: no lock file, no constraints file, no CI pin,
and `requires-python >=3.11` is compatible.

**The mixin methods deliberately omit `@_handle_github_errors`.** This is the
one documented departure from every other `IssueManager` method. That decorator
(`base_manager.py:78-90`) re-raises only 401/403 and *swallows every other*
`GithubException`, replacing it with `default_return` — it would discard exactly
the 404 and 422 text this feature must surface. Instead `GithubException`
propagates and the server tool renders the message. A code comment in the mixin
says so, pointing at `base_manager.py:78`. Do not "fix" this back.

`github_issue_edit`'s alternative machinery (sentinel + `attempted_writes` +
re-read) exists because its writes are non-atomic; these calls are single, so it
buys nothing here and is not used.

**No new TypedDicts — the mixin returns PyGithub objects.** `types.py` is
untouched. `github_pr_view` (`server.py:985-995`) and `github_search`
(`server.py:1109-1119`) already read raw PyGithub objects in `server.py`, so
this is the established local style and it avoids two type definitions plus two
conversion loops.

| Mixin method | Returns | `None` means |
|---|---|---|
| `add_sub_issue` / `remove_sub_issue` | `Optional[Issue]` — the **refetched** parent | repository inaccessible |
| `list_sub_issues` | `Optional[List[SubIssue]]` | repository inaccessible |

`None` for an inaccessible repository is the existing `_get_repository()` idiom,
and it keeps "no sub-issues" (`[]`) distinguishable from "could not read the
repo", which the server renders via the existing `_repo_access_error(manager)`.

**Shared helpers instead of three near-copies**, at both layers:

- Mixin: `add_sub_issue` and `remove_sub_issue` differ by one line, so both are
  thin wrappers over a module-level `_write_link(manager, parent, child, unlink)`
  holding the validate → fetch-both → guard → write → refetch sequence once.
- Server: `_subissue_write(parent_number, child_number, unlink, reference_name)`
  holds the inline validation, manager build, error rendering and success line;
  the two write tools are one-liners over it. `_api_error(exc, reference_name)`
  is shared by all three tools.

The shared mixin logic is **module-level functions taking the manager**, not
private methods on the mixin: a mixin annotates `self: "BaseGitHubManager"`
(see `comments_mixin.py`), and `BaseGitHubManager` does not declare the mixin's
own helpers, so `self._write_link(...)` would not type-check.

**`sub_issues_summary` needs a `cast`, confined to one three-line function.**
PyGithub declares the property `-> SubIssueSummary` (non-Optional) but returns
`None` at runtime when the payload lacks the key — `Attribute[SubIssueSummary]`
stays `NotSet` and `.value` yields `None`. With `strict = true` and
`warn_unreachable = true` (`pyproject.toml:148-149`, and the `tests.*` override
at `158-162` does not cover `src/`), a plain `if summary is None:` is flagged
`unreachable` under the CI mypy run. `sub_issue_total()` reads it through
`cast(Optional[SubIssueSummary], ...)`, which names the real cause — the
library's annotation is wrong — where a bare `# type: ignore[unreachable]` would
only silence it. One cast, one place, directly unit-testable with a real `None`.

**Two deliberate readings of the issue, both flagged:**

1. *The pull-request guard cannot live where the issue words it.* The issue puts
   it under "Pre-write validation, in `server.py`, before the manager is built",
   alongside the positive-number and self-link checks — but `issue.pull_request`
   requires a fetched issue, which requires the manager. The two pure-argument
   checks stay inline in the tool before `_issue_manager(...)`; the PR guard
   lives in the mixin, raising `ValueError("#<n> is a pull request, not an
   issue")`, which the tool's catch renders into the decided string byte for
   byte. Nothing is written first either way.
2. *The tools catch `Exception`, a superset of Decision 16's
   `(GithubException, ValueError)`.* Both named types are still caught and still
   rendered as `"Error: <message>"`; `_api_error` falls back to `str(exc)` when
   there is no dict `message`, which is exactly what a `ValueError` needs. Every
   other tool in `server.py` already ends in `except Exception` (lines 893, 948,
   1027, 1136) with no pylint disable, so this is both simpler than two arms and
   consistent with the file.

**Message rendering stays inline.** `_api_error` guards with
`isinstance(data, dict)` and `.get("message")`, falling back to `str(exc)` —
`exc.data` is not reliably a dict with a `message` key. The shared
`github_operations/exception_renderer.py:render_exception_for_display` is *not*
reused: it emits `"GithubException 422 — msg"`, a format asserted by two
existing test files, and this feature has settled on `"Error: <msg>"`. Changing
a shared helper's contract for three new tools is not worth it.

**Every error string appends `_ref_suffix(reference_name)`** (`server.py:84`),
as every other issue tool does, so the caller knows which repo failed.

**Both issues are fetched with `self._get_issue_checked(repo, n)`**, never
`repo.get_issue(n)`, so parent and child both get the transferred-issue guard
(GitHub answers a transferred issue's old URL with a 301 that PyGithub follows
silently). The resulting `IssueIdentityMismatchError` subclasses `ValueError`.

**Validation lives at two layers on purpose.** `validate_issue_number`
(`issues/base.py`) *raises* `ValueError` and is used inside the mixin; the
server tools do their own inline `if number <= 0: return "Error: ..."` and
return a string. One function cannot serve both.

**`max_results` is clamped and sliced exactly as `github_search` does** —
`max(0, max_results)` then `islice` over the `PaginatedList`, so a default call
never fetches a page just to discard it.

**Pre-existing infrastructure that needs no change** (verified): tool
registration is just `@mcp.tool()` + `@log_function_call` on a module-level
function — no tool list and no `issues/__init__.py` export;
`.importlinter`'s `pygithub_isolation` already ignores
`mcp_workspace.github_operations.**` and `tach.toml` has `exact = false`, so no
contract changes; `server.py` is allowlisted for file size;
`docs/ARCHITECTURE.md` mentions neither mixins nor individual tools.
`vulture_whitelist.py` **does** need the three names — it is a required gate.

## Output formats

Success:

- add — `Linked #<child> as a sub-issue of #<parent> — <parent_url> (<N> sub-issues)`
- remove — `Unlinked #<child> from #<parent> — <parent_url> (<N> sub-issues)`
- list — one line per child, `#<number>  <state>  <title>` (two spaces), or `No sub-issues.`

`N` is `sub_issues_summary.total` on the refetched parent — the cheap
confirmation that the link landed server-side rather than merely not erroring.
When the summary is `None` the whole parenthetical is omitted: no invented
`(0 sub-issues)`, no extra API call. The refetch is required because
`add_sub_issue` returns the *child* `SubIssue`, so the pre-write parent's
summary would be off by one.

Errors, each with `_ref_suffix` appended:

- `Error: invalid issue number: <n>` — either number not positive
- `Error: an issue cannot be its own sub-issue`
- `Error: #<n> is a pull request, not an issue`
- `Error: Could not access repository (tried <api_base_url>)` — via `_repo_access_error`
- `Error: <GitHub's message>` — 404 (unknown number), 422 (already linked to
  this or another parent, or a cycle), 404 on removing an unlinked child

The already-linked 422 is one generic message from GitHub —
`"Issue may not contain duplicate sub-issues and Sub issue may only have one
parent"` — with nothing distinguishing "linked here" from "linked elsewhere".
Report both identically rather than inventing a false distinction; a caller who
needs to know calls `github_subissue_list` first. A remove that matches nothing
is reported as an error, not smoothed into a silent no-op.

## Files created / modified

Created:

- `src/mcp_workspace/github_operations/issues/sub_issues_mixin.py`
- `tests/github_operations/issues/test_sub_issues_mixin.py`
- `tests/github_operations/test_github_write_tools_subissues.py`

Modified:

- `src/mcp_workspace/github_operations/issues/manager.py` — compose the mixin
- `src/mcp_workspace/server.py` — `_api_error`, `_subissue_write`, three tools
- `pyproject.toml` — `PyGithub>=2.1.0` → `>=2.7.0`
- `vulture_whitelist.py` — the three tool names
- `tests/github_operations/test_github_write_tools_reference.py` — routing cases
- `README.md` — tool table (~line 246)
- `tests/LLM_Test.md` — Section 4 and the reference-project section
- `.claude/CLAUDE.md` — tool-mapping table

Untouched on purpose: `issues/types.py`, `issues/__init__.py`,
`exception_renderer.py`, `.importlinter`, `tach.toml`, `docs/ARCHITECTURE.md`.

## Steps

| Step | Scope | Commit |
|---|---|---|
| [step_1](./step_1.md) | `SubIssuesMixin` + composition + dependency floor + mixin tests | 1 |
| [step_2](./step_2.md) | Three MCP tools + server helpers + vulture whitelist + tool tests | 1 |
| [step_3](./step_3.md) | `reference_name` routing tests | 1 |
| [step_4](./step_4.md) | Documentation (README, LLM_Test.md, CLAUDE.md) | 1 |

Each step is tests-first, self-contained, and ends with all quality gates
passing: `run_format_code`, then pylint, pytest (`-n auto`), mypy, vulture,
ruff, lint-imports.
