# Security Policy

## Reporting a Vulnerability

Report vulnerabilities through GitHub private vulnerability reporting only: in this repository, go to **Security → Report a vulnerability**.

Do not open public issues for security problems.

## Response

Reports are handled on a best-effort basis. There is no fixed response time.

## Supported Versions

Only the latest release on PyPI receives security fixes.

## Threat Model

`mcp-workspace` is a local MCP server. It runs over stdio under the user's account, with that account's file permissions and the configured GitHub token. It does not authenticate its client, normally an LLM agent, and carries out any request the restrictions below allow.

Treat the agent as influenceable. Issue bodies, PR comments, file content and git output can all carry prompt injection written by someone else. An agent that follows such text can do whatever the tools permit: change or delete project files, and write to GitHub with the token.

## Intended Restrictions

The server is meant to enforce the following. A way around any of them is a vulnerability.

File tools:

- Workspace file tools stay inside the project directory. Reference project file tools stay inside that reference project and only read. See [Path Confinement](README.md#path-confinement).
- Workspace file tools refuse the `.git` directory and paths matched by the project root's `.gitignore`.
- `delete_directory` refuses the project root.

`git` tool:

- It accepts a fixed set of subcommands, read commands plus `fetch`, and checks flags against a per-command allowlist.

GitHub tools:

- `github_issue_view` fences text from untrusted authors in `<untrusted>` tags, and issue list and search tools mark their rows. These are labels for the agent, not enforcement. File content and git output carry no such label.
- `github_pr_view` and `check_branch_status` withhold PR text from untrusted authors. See [Commenter trust](README.md#commenter-trust).
- `reference_name` accepts only configured reference projects.
- Issue tools refuse `status-*` labels.
- The `/approve` workflow only acts on comments from `OWNER`, `MEMBER` or `COLLABORATOR`.

## Credentials

The GitHub token comes from the `GITHUB_TOKEN` environment variable, otherwise from `[github] token` in the user config file. See [GitHub configuration](README.md#github-configuration). Protecting that file and limiting the token's scope is up to the user: the server can do on GitHub whatever the token allows.

## Scope

In scope are bypasses of the restrictions above, such as:

- reading or writing outside the project or reference project with any tool
- workspace file tools reaching `.git` or gitignored paths
- the `git` tool changing anything beyond what `fetch` updates
- getting untrusted text shown to the agent as trusted
- changing an issue's status label through these tools, or promoting an issue without being trusted
- credential handling

Out of scope:

- an agent misusing tools it is allowed to use, including after prompt injection, unless a restriction above was bypassed
- anything requiring prior access to the user's account, config file or environment
- what a token can do within its own permissions
- the limitation documented under [Path Confinement](README.md#path-confinement)
