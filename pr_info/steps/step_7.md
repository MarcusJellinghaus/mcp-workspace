# Step 7: README docs

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement `pr_info/steps/step_7.md` only.
> Docs only, no code. Run pylint, pytest (`extra_args: ["-n", "auto"]`) and mypy to confirm
> nothing broke, then make exactly one commit for this step.

## WHERE

- `README.md`, section `## GitHub configuration`

## WHAT

1. Add two bullets to the `[github]` key list:
   - `traffic_log`: `true` writes one line per GitHub HTTP request to a daily file. Off by
     default. Read once per process; no environment-variable override; independent of
     `--log-level`.
   - `traffic_log_dir`: folder for the files. Default `<app-data>/mcp_coder/logs/github_traffic/`.
2. Add both keys to the TOML example (`traffic_log_dir` commented out).
3. New subsection `### GitHub traffic log`:
   - file name `github_requests_YYYY-MM-DD.log` (local date); several processes and machines
     may append to the same folder
   - the line format and example from `summary.md`
   - fields: local ISO timestamp, pid, command (set by the calling application;
     `mcp-workspace server` for this server; blank when unset), method and path with query,
     status, `X-RateLimit-Resource` / `X-RateLimit-Remaining` (`-` when missing), duration,
     call chain (`mcp_coder` / `mcp_workspace` frames, outermost first)
   - status values: HTTP status; `retry <status>` or `retry <ExceptionType>` when another
     attempt follows (duration `-`); `ERR <ExceptionType> [status]` on failure. The wait-cap
     failure shows as `ERR RateLimitExceededExceedsMaxWait`.
   - redirect and 202 hops: each hop gets its own line; the line of the request that led to a
     hop repeats the final hop's status and headers, and its duration is cumulative (for 202
     it includes PyGithub's 2 s wait)
   - never written: token, auth headers, request/response bodies, GraphQL query text, query
     strings of requests to hosts other than the API host (the signed blob URL a 302
     redirects to); API request lines keep their query
   - a write failure skips the line and never affects the request

## HOW / ALGORITHM / DATA

Not applicable (docs only). Keep the style of the surrounding README: short bullets, no filler.
