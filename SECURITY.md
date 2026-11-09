# Security Policy

## Reporting a Vulnerability

Report vulnerabilities through GitHub private vulnerability reporting only: https://github.com/MarcusJellinghaus/mcp-workspace/security/advisories/new (in this repository, **Security → Report a vulnerability**).

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
- Workspace file tools and reference project reads refuse any `.git` entry, under any spelling or through a link, and paths matched by the root `.gitignore` of that project. Listing a subdirectory is the exception described in [Path Confinement](README.md#path-confinement): it can show file names, not content.
- The root `.gitignore` itself is writable, so an agent that edits it changes which paths are refused.
- `delete_directory` refuses the project root. It and `move_file` refuse a directory that contains a `.git` entry.

`git` tool, on the workspace and on reference projects alike:

- It accepts a fixed set of subcommands, read commands plus `fetch`.
- It checks flags against a per-command allowlist, short flags one letter at a time. Only flags that take a value may have one attached, in the expected format.
- For commands that take paths, operands and pathspecs must be relative, stay inside the repository, and not name a `.git` entry. Git's own object store is readable, so anything committed can be shown. `status` and `ls_files` can show the names of gitignored files, not their content.
- `fetch` and `ls_remote` accept only configured remote names, not URLs or paths. `fetch` refspecs cannot name a destination or force an update, and shallow-history flags are refused, so a fetch updates only remote-tracking refs, tags and `FETCH_HEAD`.
- `branch` only lists: a name is accepted only with a flag that puts git in list mode.

GitHub tools:

- `github_issue_view` fences text from untrusted authors in `<untrusted>` tags, and issue list and search tools mark their rows. These are labels for the agent, not enforcement. File content and git output carry no such label.
- `github_pr_view` and `check_branch_status` withhold PR text from untrusted authors. See [Commenter trust](README.md#commenter-trust).
- `reference_name` accepts only configured reference projects.
- General issue tools refuse `status-*` labels. Only `github_issue_set_status` changes them, and only to a label that already exists in the target repository.
- The `/approve` workflow only acts on comments from `OWNER`, `MEMBER` or `COLLABORATOR`.

## Credentials

The GitHub token comes from the `GITHUB_TOKEN` environment variable, otherwise from `[github] token` in the user config file. See [GitHub configuration](README.md#github-configuration). Protecting that file and limiting the token's scope is up to the user: the server can do on GitHub whatever the token allows.

The API host comes from the repository's `origin` remote. The token is sent only to `github.com`, `*.ghe.com` and hosts listed in `[github] enterprise_hosts`.

Credentials embedded in remote URLs (`https://user:token@host/...`) are removed from `get_reference_projects`, `git fetch` and `ls_remote` output, and from error messages.

## Scope

In scope are bypasses of the restrictions above, such as:

- reading or writing outside the project or reference project with any tool
- file tools reaching `.git` or the content of gitignored paths
- the `git` tool changing anything beyond what `fetch` updates
- getting untrusted text shown to the agent as trusted
- changing an issue's status label through any tool other than `github_issue_set_status`, or promoting an issue without being trusted
- credential handling

Out of scope:

- an agent misusing tools it is allowed to use, including after prompt injection, unless a restriction above was bypassed
- anything requiring prior access to the user's account, config file or environment
- what a token can do within its own permissions
- the limitation documented under [Path Confinement](README.md#path-confinement)
- editing the root `.gitignore` to lift its rules
