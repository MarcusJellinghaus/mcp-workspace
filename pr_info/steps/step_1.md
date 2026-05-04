# Step 1 — `RepoIdentifier.web_host` property

**Goal:** Add a `web_host` property to `RepoIdentifier` that resolves the *web origin* (no `api.` subdomain, no `/api/v3` path) for the three host branches. Used by Step 2's 404 hint to build the settings URL on `github.com` / `*.ghe.com`.

This step is fully independent of the probe work and can land as its own commit.

## WHERE

**Modify:**
- `src/mcp_workspace/utils/repo_identifier.py`
- `tests/utils/test_repo_identifier.py`

## WHAT

New property on `RepoIdentifier`:

```python
@property
def web_host(self) -> str | None:
    """Web origin for fine-grained PAT settings URL.

    Returns None on GHES — settings page does not exist there.
    """
```

**Return values:**
| Hostname | `web_host` |
|---|---|
| `github.com` | `"https://github.com"` |
| `tenant.ghe.com` (any `*.ghe.com`) | `"https://tenant.ghe.com"` (NO `api.` prefix) |
| `ghe.corp.com` (any other) | `None` |

> **Asymmetry note:** `web_host` is NOT symmetric with `api_base_url`. `*.ghe.com` produces `https://api.<tenant>.ghe.com` for API but `https://<tenant>.ghe.com` for web. The `web_host` property must NOT prepend `api.`.

> **Design decision:** GHES returns `None` (rather than `https://<host>`). The classifier in Step 2 uses `web_host is None` as the signal to suppress the fine-grained-PAT explanation and the settings URL. This pre-computes the host-classification rule in exactly one place.
>
> User-confirmed deviation from issue text (which suggested `https://<host>` for GHES). Rationale: returning `None` consolidates the host-class decision into the property; the classifier becomes a dumb consumer (`if web_host is None: GHES branch; else: fine-grained branch`). Note this deviation in the eventual PR description.

## HOW

- Implement as a `@property` on `RepoIdentifier` (same dataclass that already exposes `api_base_url`, `https_url`, etc.).
- Lowercase the hostname for the `*.ghe.com` and `github.com` checks (matches the casing logic in `hostname_to_api_base_url`).
- Emit a `logger.debug(...)` line per branch matching the format already used in `hostname_to_api_base_url` (input, normalized, branch, url).

## ALGORITHM

```text
h = self.hostname.lower()
if h == "github.com":
    return "https://github.com"
if h.endswith(".ghe.com"):
    return f"https://{h}"          # NO "api." prefix
return None                         # GHES has no settings page
```

## DATA

- Input: `self.hostname: str` (already on the dataclass).
- Output: `str | None`.
- No new fields, no breaking changes. Existing `api_base_url` / `https_url` / `cache_safe_name` properties unchanged.

## Tests (TDD — write before the implementation)

Add a new test class `TestWebHost` in `tests/utils/test_repo_identifier.py`:

```python
class TestWebHost:
    @pytest.mark.parametrize(
        "hostname,expected",
        [
            ("github.com",     "https://github.com"),
            ("GitHub.com",     "https://github.com"),
            ("tenant.ghe.com", "https://tenant.ghe.com"),
            ("Foo.GHE.com",    "https://foo.ghe.com"),
            ("ghe.corp.com",   None),
            ("github.example.org", None),
        ],
    )
    def test_web_host(self, hostname: str, expected: str | None) -> None: ...

    def test_ghe_cloud_no_api_prefix(self) -> None:
        # Explicit assertion that *.ghe.com web host does NOT contain "api."
        repo = RepoIdentifier(owner="o", repo_name="r", hostname="tenant.ghe.com")
        assert repo.web_host is not None
        assert "api." not in repo.web_host
        assert repo.web_host == "https://tenant.ghe.com"

    def test_debug_log_emitted(self, caplog: pytest.LogCaptureFixture) -> None:
        # Mirror existing TestHostnameToApiBaseUrlDebugLogging style
        ...
```

## Quality checks (mandatory after edit)

```text
mcp__tools-py__run_pylint_check
mcp__tools-py__run_pytest_check  (extra_args=["-n", "auto", "-m", "not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"])
mcp__tools-py__run_mypy_check
```

All three must pass. No new pylint/mypy warnings introduced.

## Commit

Single commit with message such as:

```
Add RepoIdentifier.web_host property for fine-grained PAT settings URL
```

## LLM Prompt

> Implement Step 1 as described in `pr_info/steps/step_1.md`, using `pr_info/steps/summary.md` for overall context.
>
> Follow strict TDD: write the new tests in `tests/utils/test_repo_identifier.py` first, confirm they fail, then add the `web_host` property to `RepoIdentifier` in `src/mcp_workspace/utils/repo_identifier.py`. After the implementation, run the three mandatory MCP quality checks (pylint, pytest with the recommended marker exclusions, mypy) and fix any issues before producing the commit.
>
> Do NOT touch `verification.py` or create `_permission_probes.py` in this step — those belong to Step 2.
