# Step 1 — Pin the MCP tool schemas in a snapshot

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_1.md`.
> Capture today's MCP tool input schemas into a JSON snapshot and add a test
> comparing against it. Do not move any tool and do not change production code.
> Run pylint, pytest (`-n auto`), mypy, ruff, then format and commit.

## Why

The issue needs proof that moving the tools didn't change any schema, so the snapshot
must be taken *before* any tool moves.

## WHERE

- `tests/toolset/__init__.py` (empty, new package)
- `tests/toolset/tool_schema_snapshot.json` (new, generated once)
- `tests/toolset/test_tool_schema_snapshot.py` (new)

## WHAT

```python
SNAPSHOT = Path(__file__).with_name("tool_schema_snapshot.json")

def _strip(node: Any) -> Any:
    """Drop 'description' and 'title' keys recursively."""

async def _current_schemas() -> dict[str, Any]:
    """{tool name: stripped inputSchema} from the live server."""

@pytest.mark.asyncio
async def test_tool_schemas_match_snapshot() -> None: ...
```

## HOW

- In this step `_current_schemas` uses `from mcp_workspace.server import mcp` and
  `await mcp.list_tools()`. Step 2 switches it to `create_server(tmp_path)`.
- Compare `inputSchema` only. Output schemas are covered by `test_tool_output_schema.py`.
- Generate the JSON once with a scratch script that reuses the same `_strip` logic:
  - Write it to `.scratch/test_make_snapshot.py`, as a test function that writes the file.
  - Run it with `run_pytest_check(extra_args=["-p", "no:cacheprovider", ".scratch/test_make_snapshot.py"])`.
  - Then `delete_directory(".scratch", recursive=True)`.
  - Write the JSON with `json.dumps(..., indent=2, sort_keys=True)` plus a trailing newline.
- No regenerate flag in the test. The snapshot is meant to stay fixed.

## ALGORITHM

```
tools = await mcp.list_tools()
current = {t.name: _strip(t.inputSchema) for t in tools}
expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
assert sorted(current) == sorted(expected)          # same 31 names
for name in expected: assert current[name] == expected[name], name
```

`_strip`: for a dict, rebuild it without the schema-annotation keys `description` / `title`,
recursing into values; for a list, recurse into each item; return anything else unchanged.
Under a `properties` key the dict maps *parameter names* to schemas: keep every key there
(a parameter may be named `title`, e.g. `github_issue_create`, `github_issue_edit`,
`github_pr_create`) and strip only inside each parameter's schema.

The test also asserts that the `title` parameter survived: `expected["github_issue_create"]["properties"]`
contains `"title"` with its type (`"string"`), it has no default, and it is listed in `required`.

## DATA

`tool_schema_snapshot.json`: `{ "<tool name>": { "type": "object", "properties": {...}, "required": [...] }, ... }`
with 31 entries.

## Checks

The new test passes with the unchanged code. All quality checks pass. One commit:
`test: pin MCP tool input schemas in a snapshot`.
