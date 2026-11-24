# Reference projects

How the reference tools read a reference project, and what to expect. Features and configuration are in the [README](../README.md#reference-projects).

## Reading at origin/\<default\>

`read_reference_file`, `list_reference_directory` and `search_reference_files` return the reference project's upstream default branch, not its working tree:

- **Ref**: `origin/HEAD`, else `origin/main`, else `origin/master`.
- **Auto-fetch**: before a read, `git fetch origin` runs if the last fetch is older than `--reference-fetch-interval-minutes` (default 15; `0` = off). A fresh clone counts as a fetch. `git(..., reference_name=...)` uses the same auto-fetch.
- **Notes**: a normal result looks like a plain read. A note is added only when the fetch failed (`[reference <name>: fetch failed (<reason>) — read origin/main @ <sha>]`, then the last fetched state is read), or when a git repository has no `origin` or no usable default branch (`[reference <name>: no usable origin default branch — read the local folder]`). `read_reference_file` puts the note on its own line after the content, `list_reference_directory` as the last entry, `search_reference_files` under a `freshness` key.
- **Tracked content only**: at the ref, untracked and gitignored local files do not exist; tracked files matching `.gitignore` are visible.
- **Plain folders**: a folder that is not a git repository is read as-is, with no note, and the local gitignore rules and `.mcp-file-access` apply as for the main project.
- **Other refs and history**: `git(command="show", args=["<ref>:<path>"], reference_name=...)` reads a file at any ref; `git(command="log", args=["-S<text>", "origin/main"], reference_name=...)` finds the commits that added or removed a string.

## Known Limitations

- After an upstream default-branch rename, reads follow the old branch until `git remote set-head origin --auto` is run in the reference project.
- With `core.autocrlf=true`, content has LF line endings where the working tree has CRLF.
- Git LFS files show their pointer text, not the file content.
- In a partial clone, reading a file downloads its missing blobs.

## Auto-Rename Behavior

If you specify duplicate reference project names, they are automatically renamed with numeric suffixes:

```bash
# This configuration:
mcp-workspace --project-dir ./project \
  --reference-project name=docs,path=./docs1 \
  --reference-project name=docs,path=./docs2 \
  --reference-project name=docs,path=./docs3

# Results in these reference project names:
# - docs (points to ./docs1)
# - docs_2 (points to ./docs2)  
# - docs_3 (points to ./docs3)
```

## Startup Validation

The server validates reference projects at startup:

- **Valid references**: Added successfully and available to the LLM
- **Invalid references**: Logged as warnings, but server continues with valid ones
- **Path resolution**: Relative paths are resolved relative to the current working directory

## Use Cases

- **Documentation browsing**: Give the LLM access to project documentation or wikis
- **Code examples**: Reference example projects or templates
- **Shared libraries**: Browse common utility libraries or frameworks
- **Configuration files**: Access system or application configuration directories
- **Multi-project development**: Work on one project while referencing related projects

## Security Notes

- Reference project *files* are **strictly read-only** - no write, edit, or delete file operations are possible
- All paths are validated to prevent directory traversal attacks: a `..` segment or a `.git` entry under any spelling is refused
- At `origin/<default>`, paths are checked lexically against the tree at that ref and only tracked content is returned — what `git show` already exposes
- When the local folder is read (not a git repository, or no usable origin default branch), the rejections described in [Path Confinement](file-access.md#path-confinement) and the reference project's own gitignore rules and `.mcp-file-access` apply
- The reference tools run `git fetch origin` over the network, at most once per fetch interval per reference project
