# Step 1 — Timeout-bounded git subprocess helper

## LLM prompt

> Read `pr_info/steps/summary.md` (design point 4) and this file. Implement step 1 only:
> write the tests first, then `git_operations/_subprocess_git.py` and the `.importlinter`
> change. Run format, pylint, pytest (`-n auto`), mypy, lint-imports and ruff; all must pass.
> Make exactly one commit.

## WHERE

- New: `src/mcp_workspace/git_operations/_subprocess_git.py`
- Modified: `.importlinter` (`[importlinter:contract:subprocess_ban]`)
- New tests: `tests/git_operations/test_subprocess_git.py`

## WHAT

```python
GIT_NETWORK_TIMEOUT: float = 120.0

class GitOutput(GitResult):
    """Result of a timeout-bounded git call; ``stdout`` is "" on failure to run."""
    stdout: str

def run_git_timed(
    project_dir: Path, *args: str, timeout: float = GIT_NETWORK_TIMEOUT
) -> GitOutput: ...
```

## HOW

- `import os, shutil, subprocess`; `from mcp_workspace.utils.url_credentials import scrub_credentials`;
  `from .core import GIT_NONINTERACTIVE_ENV, GitResult, logger`.
- Follow `verification.py` `_run`: `stdin=subprocess.DEVNULL`, `capture_output=True`,
  `text=True`, `encoding="utf-8"`, `errors="replace"`, `check=False`, `timeout=timeout`,
  `cwd=project_dir`, `env={**os.environ, **GIT_NONINTERACTIVE_ENV}`, `# noqa: S603`.
- Log only `args[0]` (the subcommand) and the timeout, never the full argv or output.
- `.importlinter`: add `mcp_workspace.git_operations._subprocess_git -> subprocess` under
  `ignore_imports`; change the contract comment to say GitPython is the default and the two
  listed modules are the only subprocess users (`_subprocess_git` for timeout-bounded network
  git, `verification` for external binaries).
- Not exported from `git_operations/__init__.py`.

## ALGORITHM

```
git = shutil.which("git"); if None -> failure("git not found on PATH")
try: proc = subprocess.run([git, *args], ...)
except TimeoutExpired: -> failure(f"git {args[0]} timed out after {timeout:g} s")
except OSError as e:   -> failure(f"git {args[0]} could not run: {e}")
out, err = scrub_credentials(proc.stdout or ""), scrub_credentials(proc.stderr or "")
ok = proc.returncode == 0 -> {success: ok, error: None if ok else f"git {args[0]} failed (exit {rc})", returncode, stderr: err, stdout: out}
```

## DATA

`GitOutput`: `success`, `error`, `returncode` (None when no process completed), `stderr`
(scrubbed, None when no process completed), `stdout` (scrubbed, `""` when none).

## Tests (write first)

Unit (patch `mcp_workspace.git_operations._subprocess_git.subprocess.run` / `shutil.which`):
- success: returncode 0 → `success=True`, stdout/stderr passed through.
- non-zero exit → `success=False`, `error == "git push failed (exit 1)"`, stderr kept.
- `subprocess.TimeoutExpired` → `error == "git push timed out after 120 s"`, `returncode is None`.
- `shutil.which` returns None → `error` mentions "not found".
- `https://user:tok@host/x` in stdout and stderr → scrubbed in both.
- the call receives `GIT_TERMINAL_PROMPT=0` in `env`, `stdin=DEVNULL`, `timeout`, `cwd`.

Integration (`@pytest.mark.git_integration`, real `tmp_path` repo via GitPython):
- `run_git_timed(repo_dir, "rev-parse", "--is-inside-work-tree")` → success, stdout `"true\n"`.

## Commit

`feat(git_operations): add timeout-bounded git subprocess helper`
