# Summary — `mcp-workspace verify` (#409)

Step 3 of epic #408. Adds `mcp-workspace verify`, a CLI subcommand that prints
`FILE ACCESS`, `GIT`, `GITHUB` and `GITHUB SECURITY` sections in the same format
as `mcp-coder verify`, and exports the section formatters plus
`github_security_rows` for mcp_coder#1444.

```
mcp-workspace verify [--project-dir DIR] [--reference-project name=..,path=..[,url=..]]... [--log-level LEVEL]
```

Example FILE ACCESS output (one row per project: workspace, accepted references
in argument order, then rejected references in argument order):

```
=== FILE ACCESS ===========================================================
  workspace              [OK]   3 rules
  mcp_coder              [OK]   absent - gitignore only
  mcp-tools-py           [ERR]  invalid (line 4: ...)
  docs                   [WARN] path not found
  bad-ref                [ERR]  rejected: inside workspace
```

Exit codes: `0` all ok; `1` a FILE ACCESS `[ERR]` row, GIT/GITHUB `overall_ok`
false, or a setup error printed as `Error: …` on stderr; `2` argparse usage
error. GITHUB SECURITY is exit-neutral.

## Architectural / design changes

1. **New package `mcp_workspace.cli`** (layer: beside `server`, below `main`).
   - `cli/__init__.py` — no imports.
   - `cli/verify_formatting.py` — git/GitHub/security labels and the section
     formatters. Imports only `mcp_coder_utils.verify_render` and stdlib, so
     mcp_coder can import it without pulling in PyGithub/GitPython.
   - `cli/verify.py` — `execute_verify(project_dir, reference_projects, rejected) -> int`.
     Runs the checks, prints the four sections, computes the exit code inline.
     Never imports `mcp_workspace.main` (no cycle).
2. **Section-formatting ownership moves here.** mcp_coder's `_format_section`
   (branch-protection child suppression, `[Permissions]` sub-header,
   `token_source` hint, `install_hint` rows) is copied verbatim as a private
   `_format_section`; three public thin wrappers expose it. Output is
   byte-identical to `mcp-coder verify` for GIT, GITHUB and GITHUB SECURITY.
3. **GitHub security row assembly moves here.** New
   `github_operations/security_rows.py` with public
   `github_security_rows(project_dir) -> dict[str, CheckResult]`: two local
   YAML file checks (dependabot config, CodeQL workflow) plus the five API rows
   of the unchanged `verify_github_security`, mapped by `_map_security_row`
   (the dead missing-key fallback is dropped). This is the only module that may
   import `yaml` (new import-linter contract).
4. **PyYAML becomes a runtime dependency** (`types-PyYAML` in `dev` and
   `typecheck` extras).
5. **`main.py` dispatch on the first token**, no argparse subparsers.
   `main()` checks `argv[0] == "verify"` before `_main()` and runs a separate,
   strict verify parser; `cli.verify` is imported lazily inside that branch.
   Server mode is unchanged except: `parse_args` runs before the
   `--project-dir` check, and an unknown token `verify` raises
   `ValueError("verify must be the first argument")`.
6. **Reference validation split.** A private core function
   `_check_reference_projects` logs as today and returns `(valid, rejected)`;
   `validate_reference_projects` is a thin wrapper returning `valid`. Rejected
   entries are `(label, reason)` tuples with short fixed reasons. Raw arguments
   are passed through `scrub_credentials` in warnings and labels.
7. **Import guard:** `import mcp_workspace.main` must not load `git`, `github`,
   `yaml` or `mcp_workspace.cli`.

## Files and folders

### Created
| Path | Purpose |
|---|---|
| `src/mcp_workspace/cli/__init__.py` | Empty package marker (docstring only) |
| `src/mcp_workspace/cli/verify_formatting.py` | Labels + `format_git_section`, `format_github_section`, `format_github_security_section`, `format_file_access_section` |
| `src/mcp_workspace/cli/verify.py` | `execute_verify` |
| `src/mcp_workspace/github_operations/security_rows.py` | `github_security_rows` + local YAML checks + `_map_security_row` |
| `tests/cli/__init__.py` | Test package marker |
| `tests/cli/test_verify_formatting.py` | Ported formatter tests |
| `tests/cli/test_verify.py` | `execute_verify` tests |
| `tests/github_operations/test_security_rows.py` | Ported security-row and probe tests |
| `tests/test_main_verify.py` | Dispatch, verify parser, verify-not-first, import guard |
| `docs/verify.md` | User documentation for `verify` |

### Modified
| Path | Change |
|---|---|
| `src/mcp_workspace/main.py` | Dispatch, verify parser, shared `--reference-project` option, `_check_reference_projects`, credential scrubbing, `parse_args` moved, epilog |
| `src/mcp_workspace/github_operations/__init__.py` | Re-export `github_security_rows` |
| `pyproject.toml` | `PyYAML` dependency; `types-PyYAML` in `dev` and `typecheck` |
| `.importlinter` | `cli` layer; `yaml` isolation contract; header contract counts |
| `tach.toml` | `cli` module, `mcp_coder_utils.verify_render` module, `main` and `tests` depends_on |
| `tests/test_main_validate_reference_projects.py` | Rejected entries + scrubbing tests |
| `README.md` | `verify` exception in the unknown-arguments note; link to `docs/verify.md` |
| `docs/ARCHITECTURE.md` | `cli` in layer diagram and table; PyYAML in Library Isolation |
| `docs/file-access.md` | Mention `mcp-workspace verify` as a way to check a rules file |
| `docs/release-notes.md` | New release-notes entry |

## Steps

1. `cli` package + `cli/verify_formatting.py` (formatters, layering config).
2. `github_operations/security_rows.py` + PyYAML + `yaml` contract.
3. `cli/verify.py` `execute_verify`.
4. `main.py`: reference validation split, verify dispatch and parser.
5. Documentation.

## Reference material (read-only, via reference project `mcp_coder`)

- `src/mcp_coder/cli/commands/verify_formatting.py` (`_LABEL_MAP`, `_BRANCH_PROTECTION_CHILDREN`, `_format_section`)
- `src/mcp_coder/cli/commands/verify_sections.py` (security helpers)
- `src/mcp_coder/cli/commands/verify.py`, `verify_exit_code.py`, `cli/main.py`
- Tests: `tests/cli/commands/test_verify_format_section_basic.py`, `test_verify_label_map.py`,
  `test_verify_render.py`, `test_verify.py::TestVerifyGithubTokenSource`,
  `test_verify_sections_security.py`, `test_verify_github_security_section.py`,
  `test_verify_github_security_probe.py`, `test_verify_exit_codes_git.py`,
  `test_verify_exit_codes_github.py`
- `mcp-coder-utils`: `src/mcp_coder_utils/verify_render.py`

Ported tests use `render_rows` plus hardcoded columns (label width 22), never
mcp_coder's conftest helpers.
