# Summary — chore(search): migrate off deprecated pathspec gitwildmatch matcher

Issue [#285](https://github.com/MarcusJellinghaus/mcp-workspace/issues/285). Follow-up to
#249 / PR #287 (merged as 22657f5).

## Goal

`src/mcp_workspace/file_tools/search.py:57` builds its glob matcher with
`PathSpec.from_lines("gitwildmatch", [...])`. In `pathspec` 1.1.1 the registered name
`gitwildmatch` is deprecated: every `search_files` / `search_reference_files` call that
passes a `glob` emits two `DeprecationWarning`s, and the name is slated for removal, which
would break both tools outright.

Replace it with the public `GitIgnoreSpec`, which uses the same pattern class without the
deprecation wrappers, and pin the absence of the warning with one test.

## Architectural / design changes

**None.** This is a like-for-like swap of one construction call inside one private helper.

- No new module, class, function, or public signature. `_match_glob(glob, files)` keeps its
  signature, its return type, and its `ValueError` contract.
- No change to the module graph: `pathspec` is already a direct dependency
  (`pyproject.toml:25`, `pathspec>=1.1.1`), and `search.py` is its only importer.
- No change to `docs/ARCHITECTURE.md` — it does not describe the matcher.
- No dependency change. No version cap is added: `GitIgnoreSpec` is public API, so a
  breaking 2.0 fails loudly at import rather than silently.

**Why `GitIgnoreSpec` and not the `"gitignore"` registry name.** The registry maps names to
different classes, so `"gitignore"` is a different matcher, not a rename:
`gitwildmatch` → `GitWildMatchPattern`, `gitignore` → `GitIgnoreBasicPattern`.
`GitWildMatchPattern` is a subclass of `GitIgnoreSpecPattern` that adds nothing but two
`@deprecated` decorators, and `GitIgnoreSpec` is declared `PathSpec[GitIgnoreSpecPattern]`
with `from_lines` defaulting to that factory — so `GitIgnoreSpec` is today's behaviour minus
the warnings, with no factory argument and no registry lookup.

`GitIgnoreBasicPattern` would change behaviour for unterminated character classes: `[`,
`[a-` and `a[b` currently compile to `regex is None` and raise; under Basic they become
valid literals that silently match nothing. That re-creates the exact failure mode #249
exists to remove, and all three are parametrized in
`test_glob_matching_nothing_by_construction_raises`.

**Behavioural surface that stays valid.** The `usable` detection triple
(`isinstance(p, RegexPattern) and p.regex is not None and p.include`) still holds:
`GitIgnoreSpecPattern` derives from `RegexPattern`. The `isinstance` arm becomes
statically redundant under the narrower generic parameter, but is deliberately left in
place — it is #249's pinned logic and rewriting it here would mix two concerns in one diff.
The win32 lowercasing is our own code and is unaffected.

**Verification comes from existing tests, not new ones.** #249 already pins current glob
behaviour in `tests/file_tools/test_search.py`; those tests passing untouched is the
evidence of a zero behaviour diff. No new glob-behaviour tests are added.

## Files created or modified

| Path | Change |
|---|---|
| `src/mcp_workspace/file_tools/search.py` | Modified — import (line 8), matcher construction (line 57), comment (line 18) |
| `tests/file_tools/test_search.py` | Modified — one new test class appended (570 lines today, 750-line cap, so no new file) |
| `pr_info/TASK_TRACKER.md` | Modified — task checkbox |

No folders or modules are created. Not modified, deliberately:

- `pyproject.toml` — dependency and version constraint stay as they are.
- `src/mcp_workspace/server.py:343,362`, `src/mcp_workspace/server_reference_tools.py:193,212`,
  `src/mcp_workspace/file_tools/search.py:24,45,162,180` — these say "gitignore/wildmatch
  semantics", meaning git's own algorithm, which stays accurate.
  `tests/test_tool_descriptions.py` pins a phrase list against both MCP tool docstrings, so
  rewording them would break that guard.
- `tests/test_tool_descriptions.py:3`, `tests/file_tools/test_search.py:149` — same usage in
  docstrings, likewise accurate.

## Steps

One step. The change is a single cohesive unit — the test and the two-line implementation it
covers cannot be committed apart without leaving a red build — so splitting it would produce
a broken intermediate commit rather than an independent part.

- [step_1.md](./step_1.md) — pin the absence of `DeprecationWarning`, then swap the matcher.

## Out of scope

- **`_compile_glob(glob)` helper.** #249's notes propose extracting one. Skipped: an
  indirection plus a `-> GitIgnoreSpec` annotation around a single call, for no gain here.
  (`PathSpec` is `Generic[TPattern_co]` in 1.1.1, so a bare `-> PathSpec` would fail mypy
  strict with `type-arg` — latent today, since the code only ever infers the type.)
- **Collapsing the `usable` detection triple.** See above.
- **Repo-wide pytest `filterwarnings`.** Rejected: would fail on `mcp`, GitPython and
  PyGithub deprecations, needing an ignore list from day one.
- **Wiki note `Repos/mcp-workspace.md`.** Its Gotchas section quotes
  `PathSpec.from_lines("gitwildmatch", ...)` by name. The substance (gitignore semantics, no
  brace expansion) survives; only that construction line goes stale. Editing `Repos/`
  requires Marcus to ask for it explicitly.
