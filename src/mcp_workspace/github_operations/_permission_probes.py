"""Per-permission read probes for verify_github.

Probes six fine-grained PAT permissions (Contents, Administration, Pull
requests, Issues, Actions, Commit statuses) by issuing a single read against
each permission's representative endpoint. Failures are classified into
hint strings naming the permission, HTTP status, and probed URL.
"""

from typing import Callable

from github.GithubException import GithubException
from github.Repository import Repository

from mcp_workspace.github_operations.base_manager import BaseGitHubManager
from mcp_workspace.github_operations.verification import CheckResult

_PROBE_KEYS: tuple[str, ...] = (
    "perm_contents_read",
    "perm_administration_read",
    "perm_pull_requests_read",
    "perm_issues_read",
    "perm_workflows_read",
    "perm_statuses_read",
)


def _classify_permission_response(
    name: str,
    status: int,
    url: str,
    web_host: str | None,
    *,
    admin_404: bool = False,
) -> CheckResult:
    """Classify an HTTP status code into a permission probe CheckResult."""
    if status == 200:
        return CheckResult(ok=True, value="OK", severity="warning")

    suffix = f" (GET {url})"
    if status == 401:
        err = f"token rejected (401) — needs {name}{suffix}"
    elif status == 403:
        err = f"blocked by org policy (403) — needs {name}{suffix}"
    elif status == 404:
        if admin_404:
            err = (
                f"missing permission {name} OR no branch protection "
                f"configured (404){suffix}"
            )
        elif web_host is not None:
            err = (
                f"missing permission {name} OR awaiting org approval "
                f"(404 — fine-grained PATs return 404 for ungranted resources; "
                f"check token at {web_host}/settings/personal-access-tokens)"
                f"{suffix}"
            )
        else:
            err = f"missing permission {name} OR resource not found (404){suffix}"
    else:
        err = f"unexpected status {status} — needs {name}{suffix}"
    return CheckResult(ok=False, value="failed", severity="warning", error=err)


def _run_probe(
    *,
    call: Callable[[], object],
    name: str,
    url: str,
    web_host: str | None,
    admin_404: bool = False,
) -> CheckResult:
    """Execute a probe call and classify the outcome."""
    try:
        call()
    except GithubException as e:
        return _classify_permission_response(
            name, e.status, url, web_host, admin_404=admin_404
        )
    except Exception as e:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        return CheckResult(
            ok=False,
            value="failed",
            severity="warning",
            error=f"network error: {e} — needs {name}",
        )
    return _classify_permission_response(name, 200, url, web_host, admin_404=admin_404)


def _probe_statuses(
    repo: Repository,
    default_branch: str,
    base: str,
    web_host: str | None,
) -> CheckResult:
    """Probe Commit statuses: Read with two-call attribution."""
    url = f"{base}/commits/{default_branch}/status"
    try:
        commit = repo.get_commit(default_branch)
    except Exception:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        return CheckResult(
            ok=False,
            value="not checked",
            severity="warning",
            error="commit lookup failed (covered by perm_contents_read)",
        )
    return _run_probe(
        call=commit.get_combined_status,
        name="Commit statuses: Read",
        url=url,
        web_host=web_host,
    )


def _probe_administration(
    repo: Repository,
    default_branch: str,
    base: str,
    web_host: str | None,
) -> CheckResult:
    """Probe Administration: Read with two-call attribution."""
    url = f"{base}/branches/{default_branch}/protection"
    try:
        branch = repo.get_branch(default_branch)
    except Exception:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        return CheckResult(
            ok=False,
            value="not checked",
            severity="warning",
            error="branch lookup failed (covered by perm_contents_read)",
        )
    return _run_probe(
        call=branch.get_protection,
        name="Administration: Read",
        url=url,
        web_host=web_host,
        admin_404=True,
    )


def run_permission_probes(
    manager: BaseGitHubManager,
    repo: Repository | None,
) -> dict[str, CheckResult]:
    """Run 6 per-permission read probes; return one CheckResult per probe key.

    When ``repo`` is None (repo_accessible.ok=False), returns 6 placeholder
    rows with value="not checked", error="repository not accessible" and
    issues NO PyGithub calls.
    """
    if repo is None:
        return {
            k: CheckResult(
                ok=False,
                value="not checked",
                severity="warning",
                error="repository not accessible",
            )
            for k in _PROBE_KEYS
        }

    identifier = manager._repo_identifier
    base = f"{identifier.api_base_url}/repos/{identifier.full_name}"
    web_host = identifier.web_host
    default = repo.default_branch

    out: dict[str, CheckResult] = {}
    out["perm_contents_read"] = _run_probe(
        call=lambda: repo.get_contents(""),
        name="Contents: Read",
        url=f"{base}/contents/",
        web_host=web_host,
    )
    out["perm_administration_read"] = _probe_administration(
        repo, default, base, web_host
    )
    out["perm_pull_requests_read"] = _run_probe(
        call=lambda: repo.get_pulls(state="all").totalCount,
        name="Pull requests: Read",
        url=f"{base}/pulls?state=all",
        web_host=web_host,
    )
    out["perm_issues_read"] = _run_probe(
        call=lambda: repo.get_issues(state="all").totalCount,
        name="Issues: Read",
        url=f"{base}/issues?state=all",
        web_host=web_host,
    )
    out["perm_workflows_read"] = _run_probe(
        call=lambda: repo.get_workflows().totalCount,
        name="Actions: Read",
        url=f"{base}/actions/workflows",
        web_host=web_host,
    )
    out["perm_statuses_read"] = _probe_statuses(repo, default, base, web_host)
    return out
