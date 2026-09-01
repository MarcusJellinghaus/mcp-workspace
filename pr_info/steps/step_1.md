# Step 1 — Extract `SearchSpec` into `github_operations/search.py`

Read `pr_info/steps/summary.md` first, in particular the **Invariants** table.

One commit: `refactor(github_search): extract SearchSpec into github_operations`

## WHERE

| Path | Action |
|---|---|
| `tests/github_operations/test_search.py` | create (write first — TDD) |
| `src/mcp_workspace/github_operations/search.py` | create |
| `src/mcp_workspace/server.py` | modify — `github_search` body (currently lines 1004–1169), and delete `import re` at line 5 |
| `tests/github_operations/test_github_search_tool.py` | modify — remove 15 tests, update module docstring |

No `tach.toml`, `.importlinter`, `vulture_whitelist.py` or `__init__.py` change.

## WHAT — `src/mcp_workspace/github_operations/search.py`

```python
"""GitHub issue-search query construction and argument validation.

Two-phase by design: from_arguments validates without needing a repository,
to_query assembles once the repository is known. The handler in server.py can
therefore reject bad input before paying for a network round-trip.
"""

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class SearchSpec:
    """Validated, normalized arguments for one GitHub issue search.

    Obtain instances through :meth:`from_arguments` only — that is what
    guarantees a query is never built from unvalidated input.

    Attributes:
        query: Caller's raw query text, sent through unmodified.
        state: Lower-cased "open", "closed", "all", or None.
        labels: Label names, never None.
        assignee: Assignee username, or None when unset or empty.
        needs_type_default: True when the query names no result type, so
            "is:issue" must be added.
        has_inline_state: True when the query already names a state inline.
    """

    query: str
    state: Optional[str]
    labels: list[str]
    assignee: Optional[str]
    needs_type_default: bool
    has_inline_state: bool

    @classmethod
    def from_arguments(
        cls,
        query: str,
        state: Optional[str] = None,
        labels: Optional[list[str]] = None,
        assignee: Optional[str] = None,
    ) -> "SearchSpec":
        """Validate and normalize search arguments.

        Args:
            query: Search query text.
            state: "open", "closed" or "all", matched case-insensitively.
            labels: Label names to AND together.
            assignee: Assignee username.

        Returns:
            A SearchSpec with normalized values and precomputed flags.

        Raises:
            ValueError: If state, query, a label or assignee is invalid. The
                message carries no "Error: " prefix — the MCP handler adds it.
        """

    def to_query(self, repo_full_name: str) -> str:
        """Assemble the GitHub search query string.

        Args:
            repo_full_name: Repository in "owner/repo" form.

        Returns:
            The complete query string, repo-scoped.
        """
```

### Design notes

- **Plain `@dataclass`**, not frozen — matches the `RepoIdentifier` precedent, and the spec is
  built and consumed two lines apart.
- **The three regexes move verbatim**, inline in `re.search(...)` calls. Do not promote them
  to compiled module constants and do not merge the two `type:`-related patterns: the
  rejection pattern must run first, and the detection pattern deliberately omits
  `type:pull-request`. A verbatim move keeps the diff reviewable as a move.
- **The "why" comments move with the code** — the live-probing rationale for rejecting
  `type:pull-request`, the "no documented escape inside a quoted qualifier" note, and the
  inline-state-wins note (including its `test_github_search_live_state_spelling_honored`
  reference). Do **not** copy the handler's 43-line MCP docstring.
- **Normalize in `from_arguments`** so `to_query` needs no None-handling: `labels or []` becomes
  a stored `list[str]`, and an empty `assignee` is stored as `None`.
- Typing follows `formatters.py` in the same package: `Optional[str]`, `list[str]`.
- `ruff` runs `D`/`DOC` (google convention) on `src/`, so every docstring needs
  `Args:`/`Returns:`, and `from_arguments` needs `Raises:`.

## ALGORITHM

`from_arguments` — check order is significant, keep it:

```
normalized = state.lower() if state else None
if normalized and normalized not in ("open", "closed", "all"): raise ValueError(msg_state)
if re.search(TYPE_PR_PATTERN, query, re.IGNORECASE):           raise ValueError(msg_qualifier)
for label in labels or []:
    if not label.strip():  raise ValueError(msg_label_blank)
    if '"' in label:       raise ValueError(msg_label_quote)
if assignee and any(c.isspace() for c in assignee):            raise ValueError(msg_assignee)
return cls(query, normalized, list(labels or []), assignee or None,
           needs_type_default=not re.search(TYPE_TOKEN_PATTERN, query, re.IGNORECASE),
           has_inline_state=bool(re.search(INLINE_STATE_PATTERN, query, re.IGNORECASE)))
```

`to_query`:

```
parts = [f"repo:{repo_full_name}"]
if self.needs_type_default: parts.append("is:issue")
parts.append(self.query)
if self.state in ("open", "closed") and not self.has_inline_state:
    parts.append(f"is:{self.state}")
parts += [f'label:"{label}"' for label in self.labels]     # always quoted: labels carry colons
if self.assignee: parts.append(f"assignee:{self.assignee}")
return " ".join(p for p in parts if p)                     # `if p` drops an empty query
```

## DATA — exact strings, copy verbatim

Regex patterns (all with `re.IGNORECASE`), unchanged from `server.py`:

```
TYPE_PR_PATTERN     r"(?:^|\s)type:pull-request(?![\w-])"
TYPE_TOKEN_PATTERN  r"(?:^|\s)(?:is:(?:issue|pr|pull-request)|type:(?:issue|pr))(?![\w-])"
INLINE_STATE_PATTERN r"(?:^|\s)(?:is|state):(?:open|closed)(?![\w-])"
```

`ValueError` messages — today's text **minus** `Error: `. Note `msg_state` interpolates the
**original** `state`, not the lower-cased one:

```python
f"Invalid state: {state}. Expected 'open', 'closed' or 'all'."
"Invalid qualifier 'type:pull-request': use 'is:pull-request' or 'is:pr'"
f"Invalid label {label!r}: a label cannot be empty or whitespace-only"
f"Invalid label {label!r}: a label containing a double quote cannot be searched"
f"Invalid assignee {assignee!r}: a GitHub username cannot contain whitespace"
```

Keep the existing line wrapping so black at 88 columns produces the same joined strings.

## HOW — `server.py` integration

Replace lines 1059–1128 of the current handler (everything from the lazy import down to and
including the `kwargs: Dict[str, str] = {...}` assignment) with:

```python
    # Lazy import: keeps PyGithub off the server startup import path
    from mcp_workspace.github_operations.formatters import format_search_results
    from mcp_workspace.github_operations.search import SearchSpec

    try:
        spec = SearchSpec.from_arguments(query, state, labels, assignee)
        manager = _issue_manager(reference_name)
        repo = manager._get_repository()  # pylint: disable=protected-access
        if not repo:
            return _repo_access_error(manager)
        kwargs: Dict[str, str] = {"query": spec.to_query(repo.full_name)}
        if sort:
            kwargs["sort"] = sort
        if order:
            kwargs["order"] = order
```

Everything below — the `# pylint: disable=protected-access` line, `search_issues(**kwargs)`,
the `islice` cap, the item dicts, the 13-line `totalCount` rationale comment, the
`format_search_results(...)` call and `except Exception as e: return f"Error: {e}"` — stays
byte-identical. The `@mcp.tool()` / `@log_function_call` decorators, the signature and the
43-line docstring are unchanged.

Then **delete `import re` from `server.py:5`.** All five `re.` uses in the file were inside
`github_search` and all three regexes have moved. Note: pylint disables the `W` category in
this repo and ruff selects only `D`/`DOC`, so neither flags an unused import here — **vulture**
is the check that catches it.

Expect the handler to land around 105 lines. The 43-line docstring and the 42-line execution
block are most of what remains; the win is layering and a testable unit, not line count.

## WHAT — `tests/github_operations/test_search.py` (write this first)

No `@patch`, no `MagicMock`, no `setup_server` fixture, no `FakeSearchResults`. Every test is
`SearchSpec.from_arguments(...)` plus either `.to_query("owner/repo")` or `pytest.raises`.

### Query-string tests — the eleven moved from `test_github_search_tool.py`

Keep them as separate named functions; each encodes a distinct rule and the bodies are already
two lines. Source name → new name, and the expected `to_query("owner/repo")` result:

| From | New name | Arguments | Expected |
|---|---|---|---|
| `test_github_search_multiple_labels` | `test_multiple_labels_each_emit_own_qualifier` | `query="bug", labels=["bug","urgent"]` | `repo:owner/repo is:issue bug label:"bug" label:"urgent"` (keep the `"labels:bug,urgent" not in` #254 regression marker) |
| `test_github_search_label_with_special_characters` | `test_label_with_colon_is_quoted` | `query="x", labels=["status-01:created"]` | `repo:owner/repo is:issue x label:"status-01:created"` |
| `test_github_search_state_emits_is_qualifier` | `test_state_emits_is_qualifier` | `query="bug", state="closed"`, then `query="bug"` | `...bug is:closed` (and `"state:" not in`), then `...bug` |
| `test_github_search_inline_state_suppresses_state_param` | `test_inline_state_suppresses_state_param` | parametrized `["bug is:closed","bug state:closed","bug IS:CLOSED","is:open bug"]`, `state="open"` | `repo:owner/repo is:issue {query}` |
| `test_github_search_qualifiers_only` | `test_empty_query_yields_qualifiers_only` | `query="", state="open", labels=["bug"]` | `repo:owner/repo is:issue is:open label:"bug"` |
| `test_github_search_state_all_emits_no_token` | `test_state_all_emits_no_token` | `query="bug", state="all"` | `repo:owner/repo is:issue bug` (and `"is:all" not in`) |
| `test_github_search_state_is_case_insensitive` | `test_state_is_case_insensitive` | parametrized `["Open","CLOSED","All"]` | `repo:owner/repo is:issue bug{token}`, token `""` for `all` |
| `test_github_search_sends_query_unmodified` | `test_explicit_is_issue_sent_unmodified` | `query="Jenkins is:issue"` | `repo:owner/repo Jenkins is:issue` |
| `test_github_search_explicit_type_suppresses_default` | `test_explicit_type_suppresses_default` | the 8 parametrized queries | `repo:owner/repo {query}` |
| `test_github_search_defaults_to_is_issue` | `test_defaults_to_is_issue` | the 6 parametrized queries | `" ".join(p for p in ("repo:owner/repo","is:issue",query) if p)` |
| `test_github_search_type_pull_request_rejection_boundaries` | `test_type_pull_request_near_misses_are_free_text` | `["type:pull-requests","release:type:pull-request"]` | `repo:owner/repo is:issue {query}` |

Drop `test_explicit_is_issue_sent_unmodified`'s `"auto-added" not in result` assertion — it is
a vestigial #254 marker against a removed auto-add block, and there is no `result` to inspect
at this level. Keep every other secondary assertion (`"labels:bug,urgent" not in`,
`"state:" not in`, `"is:all" not in`) — they are cheap and read on the query string.

### Validation tests — the four moved

Flatten into **one** parametrized function. All four share the shape "bad input → exact
message", and the per-case rationale now lives as comments next to the code in `search.py`:

```python
@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"query": "x", "labels": ["bug", 'needs "review"']},
         'Invalid label \'needs "review"\': '
         "a label containing a double quote cannot be searched"),
        # blank labels: "", "   ", "\t"  -> Invalid label {label!r}: a label cannot be
        #                                   empty or whitespace-only
        # whitespace assignees: "john doe", " alice", "alice\tb"
        #                               -> Invalid assignee {assignee!r}: a GitHub
        #                                  username cannot contain whitespace
        # type:pull-request: "type:pull-request", "fix type:pull-request",
        #                    "TYPE:PULL-REQUEST"
        #                               -> Invalid qualifier 'type:pull-request': use
        #                                  'is:pull-request' or 'is:pr'
    ],
)
def test_from_arguments_rejects_invalid_input(kwargs, message) -> None:
    with pytest.raises(ValueError) as excinfo:
        SearchSpec.from_arguments(**kwargs)
    assert str(excinfo.value) == message
```

Use `str(excinfo.value) == message`, **not** `pytest.raises(match=...)` — `match` is a regex
search and would not preserve the byte-identical guarantee.

`test_github_search_invalid_state` does **not** move; it stays at handler level as the
ordering guard (see below).

No separate test for `needs_type_default` / `has_inline_state`: the eleven `to_query` tests
already observe both flags, and asserting them directly would restate the same facts. The
fields stay public as the issue specifies.

## HOW — trim `tests/github_operations/test_github_search_tool.py`

Delete these 15 test functions (11 query-string + 4 validation) — they are now in
`test_search.py`:

```
test_github_search_multiple_labels
test_github_search_label_with_special_characters
test_github_search_label_with_embedded_quote
test_github_search_label_empty_or_blank
test_github_search_state_emits_is_qualifier
test_github_search_inline_state_suppresses_state_param
test_github_search_qualifiers_only
test_github_search_state_all_emits_no_token
test_github_search_state_is_case_insensitive
test_github_search_rejects_assignee_with_whitespace
test_github_search_sends_query_unmodified
test_github_search_explicit_type_suppresses_default
test_github_search_defaults_to_is_issue
test_github_search_rejects_type_pull_request
test_github_search_type_pull_request_rejection_boundaries
```

Keep, unchanged:

- `test_github_search_basic` — result rendering plus one wiring check
  (`query == "repo:owner/repo is:issue fix"`).
- `test_github_search_with_qualifiers` — its `sort`/`order`-stay-kwargs and
  `state`/`labels`/`assignee`-are-not-kwargs assertions are handler-level and cannot move.
- `test_github_search_empty`, `test_github_search_issue_vs_pr_indicator`,
  `test_github_search_error`, `test_github_search_no_repo`.
- `test_github_search_invalid_state` — **the ordering guard.** Its
  `_get_repository.assert_not_called()` and exact `Error: Invalid state: bogus. Expected
  'open', 'closed' or 'all'.` assertion are the one end-to-end check that the `ValueError`
  still renders byte-identically and that validation still precedes the network call.
- The `live_repo_root` fixture and the three `@pytest.mark.github_integration` tests.

Update the module docstring (lines 1–6) to point query-construction and validation-message
coverage at `test_search`, keeping the existing note about
`test_github_read_tools_pr_search` and the file-size reason the modules stay separate.

Leave the imports alone: `re` is still used at line 596 in a live test, and `Path`,
`FakeSearchResults`, `MagicMock`, `patch` all still have users. The file drops from 683 to
roughly 380 lines, comfortably under the 750 CI limit.

## Checks

`run_format_code`, then `run_pylint_check`, `run_pytest_check` (`extra_args: ["-n", "auto"]`),
`run_mypy_check`, `run_vulture_check`, `run_ruff_check`, `run_lint_imports_check`,
`run_tach_check`. `tests/test_startup_performance.py` must still pass — it is the guard on the
lazy import.

## LLM prompt

> Implement step 1 of issue #264. Read `pr_info/steps/summary.md` (especially the Invariants
> table) and `pr_info/steps/step_1.md` in full before writing anything.
>
> Work TDD: write `tests/github_operations/test_search.py` first and confirm it fails on the
> missing module, then create `src/mcp_workspace/github_operations/search.py`, then rewrite the
> `github_search` handler body in `src/mcp_workspace/server.py` and delete `import re` from
> line 5, then delete the 15 listed tests from
> `tests/github_operations/test_github_search_tool.py` and update its module docstring.
>
> This is a pure refactor: every query string and error message must stay byte-identical, and
> `SearchSpec.from_arguments` must be the first statement inside the handler's `try`, ahead of
> `_issue_manager`. Import `search.py` inside the handler body, never at module top level. Do
> not touch `tach.toml`, `.importlinter`, `docs/ARCHITECTURE.md`, `vulture_whitelist.py`,
> `github_operations/__init__.py`, `test_github_read_tools_pr_search.py` or
> `test_github_read_tools_reference.py`.
>
> Run `run_format_code`, then pylint, pytest (`-n auto`), mypy, vulture, ruff, lint-imports and
> tach. All must pass. Then stage and commit as
> `refactor(github_search): extract SearchSpec into github_operations`.
