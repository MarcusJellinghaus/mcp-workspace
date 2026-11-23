# Step 3 — Gitignore refusal hint and invalid-file note (gaps 5a, 5b, 6)

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement **only** `pr_info/steps/step_3.md`.
> Write the tests first, then the code. Run pylint, pytest (`-n auto`) and mypy until all pass,
> run `run_format_code`, and make exactly one commit.

## Goal

The gitignore refusal tells the **user** how to expose a path. In a reference project it names
that project's rules file and `list_reference_directory()`. While the rules file is invalid, the
refusal shows the problems instead of the hint, with identical text whether the path exists or not.

## WHERE

- `src/mcp_workspace/file_tools/file_access.py` (receives `_excluded_error`)
- `src/mcp_workspace/file_tools/directory_utils.py` (loses `_excluded_error`)
- `src/mcp_workspace/toolset/reference.py`, `src/mcp_workspace/toolset/read.py`
- `tests/file_tools/test_file_access.py`, `tests/test_reference_path_rules.py`, `tests/test_file_access_tools.py`
- `docs/file-access.md`, `docs/release-notes.md`

## WHAT

```python
# file_access.py (moved from directory_utils.py)
def _excluded_error(
    file_path: str, problems: Sequence[str] = (), reference: bool = False
) -> ValueError:
    """Build the refusal for a path hidden by gitignore rules."""

def require_access(
    file_path: str, project_dir: Path, needed: FileAccess, *, reference: bool = False
) -> None: ...
```

## HOW

- **Move `_excluded_error`:** delete it from `directory_utils.py`, define it in `file_access.py`,
  and drop it from `file_access`'s import list from `directory_utils`. Use
  `collections.abc.Sequence` and `ACCESS_RULES_FILE`.
- **`require_access`:** keep `rules = load_access_rules(project_dir)` in a variable. The hidden
  branch becomes `raise _excluded_error(file_path, rules.problems, reference)`. Document
  `reference` in Args: "True for a reference project: names that project's rules file and
  `list_reference_directory()`".
- **`list_accessible_files`:** call `_excluded_error(str(directory), rules.problems)`. It needs no
  reference context, because reference tools only list `"."`.
- **`toolset/reference.py`, `read_reference_file`:** call
  `require_access(file_path, ref_path, FileAccess.READ_ONLY, reference=True)`.
- **`toolset/read.py`, `list_directory`:** change the comment "A hidden file keeps the gitignore
  message" to "A hidden file gets read_file's refusal".
- Build the text from `rules.problems` only, never from the `_access` reason string.

## ALGORITHM (`_excluded_error`)

```
rules_file = f"that project's {ACCESS_RULES_FILE}" if reference else ACCESS_RULES_FILE
list_tool  = "list_reference_directory()" if reference else "list_directory()"
head = f"Path '{file_path}' is excluded by .gitignore rules and cannot be accessed"
if problems: middle = f"; {rules_file} is invalid ({'; '.join(problems)}), so no rule exposes it."
else:        middle = f". The user can expose it with a rule in {rules_file}."
return ValueError(f"{head}{middle} Use {list_tool} to see available files.")
```

## DATA — exact messages

- `Path 'b.log' is excluded by .gitignore rules and cannot be accessed. The user can expose it with a rule in .mcp-file-access. Use list_directory() to see available files.`
- `Path 'b.log' is excluded by .gitignore rules and cannot be accessed. The user can expose it with a rule in that project's .mcp-file-access. Use list_reference_directory() to see available files.`
- `Path 'b.log' is excluded by .gitignore rules and cannot be accessed; .mcp-file-access is invalid (line 1: unknown level 'readonly'), so no rule exposes it. Use list_directory() to see available files.`
- `Path 'b.log' is excluded by .gitignore rules and cannot be accessed; that project's .mcp-file-access is invalid (line 1: unknown level 'readonly'), so no rule exposes it. Use list_reference_directory() to see available files.`

## Tests (write first)

**`tests/file_tools/test_file_access.py`:** assert the exact strings above.
- Each of the four cases via `require_access` (`reference=False/True`, valid/invalid rules).
- **No existence leak:** two projects with the same `.gitignore` `secret/` and the same invalid rules
  file; one has the directory `secret/`, the other doesn't.
  `str(require_access("secret", A, READ_ONLY) error) == str(list_accessible_files("secret", B) error)`.
- A gitignored and invalid `.mcp-file-access` itself: the refusal of `require_access(".mcp-file-access", …)`
  contains `is invalid (` and not `The user can expose`. This is the case where the `built-in`
  reason comes back before the invalid check.

**Tool-level checks:**
- **`tests/test_reference_path_rules.py`:** `read_reference_file("ref", ".env")` raises a message containing
  `that project's .mcp-file-access` and `list_reference_directory()`.
- **`tests/test_file_access_tools.py`:** `check_body_target` on a gitignored, unexposed path raises
  a message containing `The user can expose it`. This covers the GitHub `body_file` path.

Existing `match="excluded by .gitignore"` tests keep passing, since the prefix is unchanged.

## Docs

**`docs/file-access.md`:**
- "Refusals": replace the sentence "Reading a hidden path keeps the gitignore message." with the
  gitignore refusal and its reference-project variant, quoted as in DATA with `<path>`.
- "Invalid rules file" list: add a bullet for the gitignore refusal, which carries the problems
  instead of the hint (quote the text).

**`docs/release-notes.md`:**
- New #404 bullet with the new gitignore refusal wordings.
- The #392 bullet "New refusal wording: …" gets ` Changed in #404, see above.`

## Commit

`feat(file_access): hint at .mcp-file-access in gitignore refusals (#404)`
