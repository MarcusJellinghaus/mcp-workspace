# Step 13 — Documentation

Docs only; no code changes.

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement **only** `pr_info/steps/step_13.md`.
> Use the MCP tools from `.claude/CLAUDE.md`. Run pytest (`extra_args: ["-n", "auto"]`) to
> confirm nothing doc-pinned broke. Run `run_format_code`, then make exactly one commit for
> this step.

## WHERE and WHAT

- `README.md`
  - Reference-tool sections: reads come from `origin/<default>`, auto-fetched every
    `--reference-fetch-interval-minutes` (default 15, `0` = off); notes appear only on a
    failed fetch or when a git repo has no usable origin default branch; plain folders are
    read as-is; `git show <ref>:<path>` and `git log -S<text>` pointers.
  - Document `--reference-fetch-interval-minutes` next to `--reference-project`.
  - Replace the old `--reference-project NAME=/path` examples, usage line and option
    description with `name=…,path=…[,url=…]`.
  - Replace "same gitignore filtering" lines for reference tools: at the ref only tracked
    content exists; the local `.gitignore` / `.mcp-file-access` apply only to the fallback.
  - Known limitations: default-branch rename (`git remote set-head origin --auto`),
    `core.autocrlf=true` LF content, Git LFS pointer text, partial clones download blobs.
  - `git log` pickaxe: `-S<text>` / `-G<regex>` (attached form only), `--pickaxe-regex`,
    `--pickaxe-all`.
- `SECURITY.md` — Intended Restrictions: reference reads at the ref return tracked content
  (what `git show` already exposes), `.git` paths refused under any spelling, `..` refused;
  gitignore refusal applies to the local fallback only. Scope bullet: reference tools fetch
  `origin` over the network.
- `docs/file-access.md` — reference listing/search "include exposed paths" applies to the
  fallback only; the `list_reference_directory` `WARNING` line appears only in the fallback;
  Path Confinement: at the ref paths are checked lexically (`ref_relative_path`), the local
  checkout is validated as before in the fallback; "Reference projects apply their own
  `.mcp-file-access`" → only when read as a local folder.
- `docs/ARCHITECTURE.md` — replace "`toolset/reference.py` calls `require_access` directly"
  with the new flow: `_reference_call` → `fetch_if_stale` → `open_ref_snapshot` →
  `file_tools` (`read_content`, `search_paths`) or the local fallback; name the new modules
  `git_operations/ref_snapshot.py`, `git_operations/origin_fetch.py`,
  `toolset/_reference_freshness.py`.
- `docs/LIBRARY_USE.md` — `tool_specs` option row `reference_fetch_interval_minutes`
  (default 15, `0` off, negative → `ValueError`); clone locks, clone-failure cache and fetch
  throttle are per `tool_specs()` call (no module globals; `clear_clone_failure_cache` is
  gone); TLS/network bullet: `workspace.reference` now runs `git fetch origin` over the
  network by default.
- `tests/LLM_Test.md` — add manual checks: read a reference file changed upstream but not
  in the local checkout; search for a symbol added upstream; `git log -S<symbol>` with
  `reference_name`; a reference folder that is not a git repo reads silently.

## Checks

Search the repo for leftover statements that become false: `search_files` for
`clear_clone_failure_cache`, `NAME=/path`, `same gitignore filtering`, and
`calls require_access directly` → none left outside `pr_info/`.
