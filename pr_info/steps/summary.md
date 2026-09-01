# Summary — #249 docs(search): glob semantics undocumented, brace patterns silently return zero matches

## Problem

`search_files` / `search_reference_files` match globs with
`PathSpec.from_lines("gitwildmatch", ...)` — gitignore semantics. Several classes of input
then produce `{"total_files": 0, "truncated": false}`, byte-identical to a genuine "no such
file":

| Input | Why |
|---|---|
| `{a,b}/f.py`, `**/*.{md,json}`, `\{a,b}/f.py` | brace expansion is a *shell* feature; braces are matched literally |
| `!*.py` | gitignore negation — a lone negated pattern matches nothing |
| `#*.py` | gitignore comment — pattern discarded |
| `""`, `"   "` | blank line — discarded |
| `[`, `[a-` | unterminated character class |

Survivable when searching *for* something. Dangerous when searching to establish an
**absence**, because the failure mode produces exactly the answer being tested for.

The tool descriptions that actually reach callers (`server.py:331`,
`server_reference_tools.py:198`) say only `File path pattern (e.g. "**/*.py")` — nothing
signals gitignore semantics.

## Solution

Documentation plus a runtime signal, split by whether a false positive is possible:

| Input | Detection | Behaviour |
|---|---|---|
| comment, blank, negation-only, pattern pathspec rejects | no usable compiled pattern | raise `ValueError` |
| `{` or an unterminated `[` present **and** zero files matched | textual | `glob_note` on the result |
| `{` or an unterminated `[` present and files matched | — | nothing |

Braces and unterminated brackets cannot raise, and cannot be detected structurally: pathspec
compiles both to a valid regex with `include is True` that matches the character literally —
`{a,b}` as a literal name, and `[` per *fnmatch(3)*, which treats invalid range notation as a
literal. Both can also be real filenames (cookiecutter ships directories literally named
`{{cookiecutter.project_slug}}`; brackets are legal filename characters) and no escape
mechanism exists.

Brace *expansion* is explicitly out of scope — it needs a cartesian product over multiple
groups, nesting, and an escape mechanism. Not a small change.

## Architectural / design changes

**One new private helper in `search.py`.** `_match_glob(glob, files) -> List[str]` absorbs
the win32 lowercasing, the `PathSpec` build, the new validation, and the matching itself.
The issue suggests `_compile_glob(glob) -> PathSpec`; returning the matched list instead
keeps the `win32` flag and the `_norm` closure together in one place rather than split
across the helper and its caller. Behaviour is identical.

**One raise site, one message.** Empty pattern list, `regex is None`, and `include is False`
all mean the same thing to a caller, and the message must be keyed on the *effect* (the
input may be neither a comment nor blank), so they collapse into a single condition and a
single `ValueError`.

`GitIgnorePatternError` — already raised today for `glob="!"` and `glob="a\\"` — subclasses
`ValueError`, so the new raises are type-consistent with existing behaviour and need no
separate handling. Part of this change is a consistency fix rather than new behaviour.

**New response key `glob_note`, separate from the existing `note`.** The two notes concern
different arguments (`glob` vs `pattern`); merging them would hide which input was suspect.
`note` and its tests are untouched. `glob_note` is computed once from `matched` and attached
to both return paths; `_search_content` needs no signature change.

**Trigger is `len(matched) == 0`, evaluated before the content search** — the same condition
in both modes. It does not fire when the glob matched files but the content search returned
nothing: if a brace or bracket glob matched files, those characters were legitimate and there
is no wrong conclusion to interrupt.

**Three docstring copies stay three copies.** MCP reads the literal docstring, so real
deduplication would mean assigning `__doc__` post-definition. A guard test asserting key
phrases in both tool descriptions buys the same protection without the magic — and the
descriptions have already drifted once (`search.py` correct, the two callers not).

**Blast radius.** `PathSpec` is used nowhere else in the repo, so the behavioural change is
confined to `search.py`. `search_reference_files` inherits it for free — both tools delegate
to the same util, and `log_function_call` logs-then-re-raises in both its sync and async
wrappers. `docs/ARCHITECTURE.md` needs no update: no module boundary, import graph, or
lazy-import path changes.

## Documented behaviours (all three docstrings)

1. Patterns use gitignore / wildmatch semantics.
2. Brace expansion is not supported — issue one call per alternative, or widen to `*` and
   filter.
3. A bare `*.py` is **unanchored** and matches at any depth. Shell users expect root-only.
4. Windows matching is **case-insensitive by design**, so a glob can never *detect* a
   filename casing mismatch — use `git ls-files`, which reports the name as recorded in the
   index. This is a cross-platform inconsistency: the same glob differs on win32 and Linux.

Each `Returns:` block also documents the `glob_note` key from step 3 — a signal the caller
cannot act on if the description never mentions it.

## Steps

| Step | Content | Commit |
|---|---|---|
| [step_1](./step_1.md) | Pin current glob semantics (tests only) | `test(search): pin gitignore glob semantics` |
| [step_2](./step_2.md) | `_match_glob` + raise on globs that match nothing by construction | `fix(search): raise on globs that match nothing by construction` |
| [step_3](./step_3.md) | `glob_note` for brace / unterminated-bracket globs with zero matches | `feat(search): flag literal-only globs that match no files` |
| [step_4](./step_4.md) | Four documented behaviours + `glob_note` in three docstrings, guard test | `docs(search): document glob semantics in tool descriptions` |

Step 1 comes first deliberately: it pins the behaviours that must survive both this change
and the follow-up matcher migration, before any production code moves.

## Files created / modified

**Modified**

- `src/mcp_workspace/file_tools/search.py` — steps 2, 3, 4 (helper, validation,
  `glob_note`, `glob` arg docstring, `Returns:`, `Raises:`)
- `src/mcp_workspace/server.py` — step 4 (`search_files` docstring only)
- `src/mcp_workspace/server_reference_tools.py` — step 4 (`search_reference_files`
  docstring only, including a `Raises:` block it does not have today)
- `tests/file_tools/test_search.py` — steps 1, 2, 3 (~370 lines today, well under the cap)

**Created**

- `tests/test_tool_descriptions.py` — step 4. New file because both natural homes are at
  the size cap: `tests/test_server.py` is 738 lines and
  `tests/test_reference_projects_mcp_tools.py` is 739.

**Conditionally modified**

- `pyproject.toml` — only if ruff DOC502 fires on the new `Raises:` blocks (see step 4).

**Unchanged**

- `docs/ARCHITECTURE.md`, `pr_info/TASK_TRACKER.md` (populated by `prepare_task_tracker`).

## Testing constraint

`pathspec` is unpinned (`>=0.12.1`), and which malformed patterns raise versus compile to a
null regex can shift between versions. Every new test asserts `search_files` behaviour —
raises, or carries `glob_note` — and never `pathspec` internals. The `regex` and `include`
attributes used for detection are public and stable, so the detection approach itself is
safe.

## Dependency

#285 (`chore(search): migrate off deprecated pathspec gitwildmatch matcher`) lands **after**
this issue. The step 1 pins plus the step 2 detection signals are exactly what makes that
migration verifiable — they are required scope here, not optional.
