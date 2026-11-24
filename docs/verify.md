# `mcp-workspace verify`

Checks a workspace setup — file access rules, git and GitHub — without
mcp_coder, or in CI. The output uses the same format as `mcp-coder verify`.

## Usage

```bash
mcp-workspace verify [--project-dir DIR] [--reference-project name=<name>,path=<dir>[,url=<url>]]... [--log-level LEVEL]
```

`verify` must be the first argument; all options come after it.
`mcp-workspace --project-dir DIR verify` stops with `verify must be the first argument`.

- `--project-dir`: workspace to check. Defaults to the current directory.
- `--reference-project`: same syntax as for the server (repeatable). See [Reference Projects](../README.md#reference-projects).
- `--log-level`: console logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL). Defaults to `WARNING`.

Logs go to the console (stderr) only; no log file is written.

Git signing is tested end-to-end: with gpg, `verify` signs a probe payload
(15 s timeout). For ssh / x509 signing the row is a warning, `not implemented for ssh/x509`.

## Sections

### FILE ACCESS

One row per project: `workspace`, then the accepted references in argument
order, then the rejected references in argument order.

```
=== FILE ACCESS ===========================================================
  workspace              [OK]   3 rules
  mcp_coder              [OK]   absent - gitignore only
  mcp-tools-py           [ERR]  invalid (line 4: ...)
  docs                   [WARN] path not found
  bad-ref                [ERR]  rejected: inside workspace
```

- A project row checks its `.mcp-file-access` (see [file-access.md](file-access.md#access-rules-mcp-file-access)).
- A reference with `url=` whose path does not exist yet shows `[WARN] path not found` — it would be cloned on first use — and does not fail the run.
- A rejected reference shows `[ERR] rejected: <reason>`, with one of:
  - `old format` — the `<name>=<dir>` form
  - `missing name`
  - `missing path`
  - `path not found` — no `url=` to clone from
  - `not a directory`
  - `same directory as workspace`
  - `inside workspace`
  - `parent of workspace`

Credentials embedded in a reference argument are scrubbed from the row label.

### GIT

Git binary, repository, identity and commit signing (including the end-to-end sign test).

### GITHUB

API base URL, network / proxy, token, authenticated user, repository access,
branch protection and token permissions.

### GITHUB SECURITY

Local dependabot config and CodeQL workflow, plus the repository's Dependabot,
secret scanning and code scanning settings. Informational: never affects the
exit code.

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | All checks ok |
| `1` | A FILE ACCESS `[ERR]` row, a failed GIT or GITHUB check, or a setup error |
| `2` | Usage error (unknown or invalid option) |

A setup error — e.g. `--project-dir` is not an existing directory, or a
reference `url=` does not match the detected remote — is printed as
`Error: …` on stderr. Unlike server startup, `verify` does not write
`logs/mcp_workspace_startup_error.log`.

## CI

Without a GitHub token (`GITHUB_TOKEN`, or `[github] token` in `config.toml`,
see [GitHub configuration](../README.md#github-configuration)) the
`Token configured` row is `[ERR]` and `verify` exits 1.
