# Step 6 — `github_label_list` tool

## Prompt for LLM

> Read `pr_info/steps/summary.md`, then implement this step
> (`pr_info/steps/step_6.md`) only. Follow TDD: write the tests first, watch them
> fail, then implement. Use MCP tools for all file and check operations.
> One commit at the end.

Independent of steps 3, 4, 5 and 7 — its test module carries its own
`setup_server` fixture, so it borrows nothing from the other write-tool steps.
Depends on step 1 for `get_available_labels`' new failure contract. This is the
only read-only tool in the set — it is here because it is what replaces
`gh label list`.

---

## WHERE

- `src/mcp_workspace/server.py` — after `github_issue_comment`
- `vulture_whitelist.py` — `_.github_label_list`
- `tests/github_operations/test_github_write_tools_labels_pr.py` — **new file**,
  shared with step 7

## WHAT

```python
@mcp.tool()
@log_function_call
def github_label_list(search: Optional[str] = None) -> str:
```

## HOW

- Backed by `IssueManager.get_available_labels()`, matching the other `github_*`
  tools. The duplication with `LabelsManager.get_labels()` is deliberately left
  alone — it is its own issue, not a detour here.
- After step 1 that function **raises** on an API failure instead of returning
  `[]`, so `No labels found.` now means only what it says. A failed lookup falls
  to `except Exception` and is reported as `Error: <msg>`.
- Filtering happens in the **tool** layer; the library function takes no filter.
- Case-insensitive substring match against name **or** description, mirroring
  `gh label list --search`.
- No formatter function — the output is one line per label, built inline.
- Docstring should note this tool only reads.
- `vulture_whitelist.py`: `_.github_label_list`.

## ALGORITHM

```
lazy import IssueManager
try:
    manager = IssueManager(project_dir=_project_dir)
    labels = manager.get_available_labels()
    if search:
        q = search.lower()
        labels = [l for l in labels if q in l["name"].lower() or q in l["description"].lower()]
    if not labels: return "No labels found."
    return "\n".join(f"{l['name']}  #{l['color']}  {l['description']}".rstrip() for l in labels)
except Exception as e: return f"Error: {e}"
```

## DATA

```
bug  #d73a4a  Something isn't working
enhancement  #a2eeef  New feature or request
```

Empty result — or an empty repo label set — renders `No labels found.`
`LabelData` is `{name, color, description, url}`; `url` is not rendered.

## Tests (TDD)

New class in `tests/github_operations/test_github_write_tools_labels_pr.py`
(create the file if step 7 has not landed yet, giving it its own autouse
`setup_server` fixture like step 3's module — fixtures are per-module, not in
`tests/github_operations/conftest.py`. The `_login_cache` reset is not needed
here: neither `github_label_list` nor `github_pr_create` resolves `@me`):

1. No `search` — every label rendered, one line each, with name, `#color` and
   description.
2. `search` matching a name — only that label.
3. `search` matching a description only — that label still returned.
4. `search` is case-insensitive.
5. `search` matching nothing → `No labels found.`
6. Empty repo label list → `No labels found.`
7. Label with an empty description — no trailing whitespace on the line.
8. Exception → `Error: <msg>`.
9. `get_available_labels` raises a 500 `GithubException` → `Error:` carrying the
   API text, **not** `No labels found.` — the pair with test 6.

## Checks

`run_pylint_check`, `run_mypy_check`, `run_pytest_check`, `run_vulture_check`.

## Commit

`Add github_label_list MCP tool`
