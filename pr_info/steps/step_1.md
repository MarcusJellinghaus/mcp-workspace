# Step 1 — Parser on markdown-it-py

## LLM prompt

> Read `pr_info/steps/summary.md` and this file (`pr_info/steps/step_1.md`). Implement
> step 1 only: write the tests first, then rewrite `parse_base_branch` on markdown-it-py,
> declare the dependency and add the startup assertion. Run pylint, pytest
> (`-n auto`) and mypy until green, run `run_format_code`, then make one commit.

## WHERE

- `pyproject.toml` — `dependencies`
- `src/mcp_workspace/github_operations/issues/base.py` — `parse_base_branch`
- `tests/github_operations/issues/test_parse_base_branch_markdown.py` (new)
- `tests/test_startup_performance.py`

## Precondition

`markdown_it` must be importable in the venv (present transitively today). If
`import markdown_it` fails in a scratch probe, write one line to `pr_info/.blocked.txt` and stop.

## WHAT

```python
# pyproject.toml dependencies
"markdown-it-py>=3.0.0",

# base.py
from markdown_it import MarkdownIt

_MARKDOWN = MarkdownIt("commonmark")
_BASE_BRANCH_HEADING = re.compile(r"base\s*branch", re.IGNORECASE)
_LINE_BREAK = re.compile(r"\r\n|\r|\n")   # markdown-it's own newline normalisation

def parse_base_branch(body: str) -> Optional[str]: ...   # signature unchanged
```

## HOW

- Module-level import in `base.py` is fine: `server.py` imports `issues` lazily, so
  `markdown_it` stays off the startup path. Add to
  `test_server_import_does_not_eagerly_load_github_or_gitpython` (or a sibling test):
  `'markdown_it': 'markdown_it' in sys.modules` → assert `False`.
- Use `re.split(_LINE_BREAK, body)`, **not** `str.splitlines()` (which also splits on
  `\x0b`, `\x0c`, ` `… and would shift `token.map` indices).
- Update the docstring: top-level ATX headings only; heading inside fences, blockquotes, list
  items or HTML comments is ignored; first matching section wins.

## ALGORITHM

```
if not body: return None
tokens = _MARKDOWN.parse(body); lines = _LINE_BREAK.split(body)
heads = [(i, t) for i, t in enumerate(tokens)
         if t.type == "heading_open" and t.level == 0 and t.markup.startswith("#")]
for k, (i, tok) in enumerate(heads):
    if _BASE_BRANCH_HEADING.fullmatch(tokens[i + 1].content.strip()):
        end = heads[k + 1][1].map[0] if k + 1 < len(heads) else len(lines)
        content = "\n".join(lines[tok.map[1]:end]).strip()
        if not content: return None
        if "\n" in content: raise MalformedBaseBranchError(content)
        return content
return None
```

## DATA

Unchanged contract: `str` branch name, `None` (absent / empty), or
`MalformedBaseBranchError(content)` (multi-line).

## Tests (new file, write first)

- fenced-only heading (```` ``` ````) → `None`
- `~~~` fenced-only heading → `None`
- fenced quote **plus** a real section → real value
- unclosed fence followed by a heading → `None`
- heading inside `<!-- … -->` → `None`
- blockquoted `> ### Base Branch` → `None`
- heading inside a list item (`- ### Base Branch`) → `None`
- `### Base Branch\n\nepic/x\n---\n` → `MalformedBaseBranchError` (setext trap)
- CRLF: `"### Base Branch\r\n\r\nfeature/v2\r\n\r\n### Next"` → `"feature/v2"`;
  CRLF two-line section → raises
- real section containing a fence → raises (content still multi-line)
- section ends at the next top-level ATX heading of any level

All existing `tests/github_operations/issues/test_base.py` tests stay green unchanged.
