# Migrate to MCP Python SDK v2 (`MCPServer` / `2026-07-28` spec)

**Type:** follow-up / tech-debt · **Depends on:** SDK v2 stable + coordinated ecosystem move (see Preconditions)

## Context

The MCP spec revision **`2026-07-28`** (finalized 2026-07-28) is the largest protocol change since launch: a **stateless core** (protocol-level sessions and `initialize` removed), a formal **extensions framework**, cacheable list results, header-based routing, and OAuth 2.0/OIDC auth hardening.

The **Python SDK v2 (`mcp` 2.0.0)** implements it and renamed the high-level server API. Verified against the `mcp-2.0.0` wheel:

- `mcp.server.fastmcp` is **removed entirely**.
- `FastMCP` → **`MCPServer`** — lives at `mcp/server/mcpserver/server.py`, re-exported as **`from mcp.server import MCPServer`**.
- The decorator API (`@app.tool()`, etc.) is **unchanged**.

Our code uses `from mcp.server.fastmcp import FastMCP` (`src/mcp_workspace/server.py:10`), so a fresh install of `mcp` 2.x fails to import. Because `uv.lock` is gitignored, CI resolved the unbounded `mcp>=1.3.0` to `2.0.0` and broke. **Interim fix already merged:** `pyproject.toml` caps `mcp>=1.3.0,<2.0.0` (resolves to 1.29.x, which still ships `fastmcp`).

This issue tracks the eventual migration off the cap onto SDK v2.

## Why not now

- SDK v2 is very fresh and sources still show beta churn (`2.0.0b1`) even though a `2.0.0` is on PyPI — the public API may still move. Migrate once it is unambiguously **stable**.
- **`mcp-coder-utils`** (shared dependency) and **`mcp-coder` #1068** (which dedups against this module) share this `mcp` dependency and must move in lockstep. A unilateral bump here would break them.
- `langchain-mcp-adapters` (as of `0.3.1`, 2026-07-27) still pins `mcp 1.28.1` — the broader Python ecosystem is still on the 1.x line.

## Backward-compatibility note (reduces risk)

A v2 `MCPServer` answers **both** the new `server/discover` and the legacy `initialize` handshake, negotiating the protocol version on the wire — so older-spec clients keep connecting with **one** v2 build (no need to fork the server). v1.x additionally receives critical + security fixes for **≥6 months** after v2 stable. Governance also guarantees **≥12 months** between a feature's deprecation and removal.

## Scope / tasks

- [ ] Bump the cap: `pyproject.toml` `mcp>=1.3.0,<2.0.0` → `mcp>=2.0.0,<3.0.0` (confirm exact stable version).
- [ ] Rename the import + constructor in `src/mcp_workspace/server.py`: `from mcp.server.fastmcp import FastMCP` → `from mcp.server import MCPServer`; `FastMCP(...)` → `MCPServer(...)`.
- [ ] Grep the whole repo (src + tests) for any other `mcp.server.fastmcp` / `FastMCP` references and update them.
- [ ] Review for reliance on **stateful** behavior (anything that assumed sessions / `initialize` lifecycle) — the stateless core removes protocol sessions. For a file-ops server this is expected to be low-risk, but confirm.
- [ ] Review whether we want to adopt any new v2 surface (extensions framework, caching/`CacheHint`, elicitation) — optional, out of scope unless there's a concrete need (YAGNI).
- [ ] Update tests + fixtures; run full checks: pylint, pytest (`-n auto`), mypy, vulture, lint-imports, file-size.
- [ ] Manual smoke test: start the server, confirm tool discovery + a couple of tool calls work end to end (verify skill / real MCP client).
- [ ] Coordinate the merge with `mcp-coder-utils` and `mcp-coder` #1068.

## Reproducibility (related, do alongside)

Because `uv.lock` is gitignored, CI has no floor against the *next* surprise major. Decide on one of: commit `uv.lock`, add a `constraints.txt`, or switch CI to `uv sync --frozen` / `uv pip install` against a pinned lock. Prevents a recurrence of this exact failure mode.

## References

- MCP `2026-07-28` spec — https://blog.modelcontextprotocol.io/posts/2026-07-28/
- SDK betas / migration — https://blog.modelcontextprotocol.io/posts/sdk-betas-2026-07-28/
- 2026 MCP roadmap — https://blog.modelcontextprotocol.io/posts/2026-mcp-roadmap/
- Python SDK (migration guide) — https://github.com/modelcontextprotocol/python-sdk
- Claude Code supports `2026-07-28` — https://claude.com/blog/bringing-mcp-2026-07-28-to-claude

## Verification / done criteria

- `pyproject.toml` allows `mcp` 2.x; no `mcp.server.fastmcp` references remain.
- All CI jobs green on a **fresh** resolve (not just the local pinned venv).
- Server smoke-tested against a real client (e.g. Claude Code on the new spec).
