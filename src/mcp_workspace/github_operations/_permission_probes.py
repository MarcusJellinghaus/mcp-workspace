"""Per-permission read probes for verify_github.

Probes six fine-grained PAT permissions (Contents, Administration, Pull
requests, Issues, Actions, Commit statuses) by issuing a single read against
each permission's representative endpoint. Failures are classified into
hint strings naming the permission, HTTP status, and probed URL.

There is deliberately no write probe. A ``perm_write`` row derived from
``repo.permissions.push`` was considered and dropped: it is unverified whether
``push`` reflects the *token's* grant or the *user's* underlying repo access,
so a read-only token on a repo you own could report ``push: true`` — a false
green that is worse than no row at all. Issue #232 makes shipping it
conditional on a one-off check with a deliberately read-only token; until that
check is run and recorded, the probe stays out.
"""

from typing import Callable

from github.GithubException import GithubException
from github.Repository import Repository

from mcp_workspace.github_operations._types import (
    CheckResult,
    ProtectionOutcome,
    is_branch_not_protected,
)
from mcp_workspace.github_operations.base_manager import BaseGitHubManager

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
) -> CheckResult:
    """Classify an HTTP status code into a permission probe CheckResult.

    Returns:
        CheckResult with ok=True for status 200; otherwise ok=False with an
        ``error`` hint naming the permission, HTTP status, and probed URL.
    """
    if status == 200:
        return CheckResult(ok=True, value="OK", severity="warning")

    suffix = f" (GET {url})"
    if status == 401:
        err = f"token rejected (401) — needs {name}{suffix}"
    elif status == 403:
        err = (
            f"not accessible (403) — needs {name}; grant it to the token, "
            f"or an org policy is blocking it{suffix}"
        )
    elif status == 404:
        if web_host is not None:
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


def _classify_exception(
    exc: Exception,
    name: str,
    url: str,
    web_host: str | None,
) -> CheckResult:
    """Classify a probe exception into a failed CheckResult.

    Returns:
        The classified HTTP status for a ``GithubException``, otherwise a
        network-error result.
    """
    if isinstance(exc, GithubException):
        return _classify_permission_response(name, exc.status, url, web_host)
    return CheckResult(
        ok=False,
        value="failed",
        severity="warning",
        error=f"network error: {exc} — needs {name}",
    )


def _run_probe(
    *,
    call: Callable[[], object],
    name: str,
    url: str,
    web_host: str | None,
) -> CheckResult:
    """Execute a probe call and classify the outcome.

    Returns:
        CheckResult from classifying the outcome's HTTP status: 200 on
        success, the ``GithubException`` status on API failure, or a
        network-error result for any other exception.
    """
    try:
        call()
    except Exception as e:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        return _classify_exception(e, name, url, web_host)
    return _classify_permission_response(name, 200, url, web_host)


def _probe_statuses(
    repo: Repository,
    default_branch: str,
    base: str,
    web_host: str | None,
) -> CheckResult:
    """Probe Commit statuses: Read with two-call attribution.

    Returns:
        CheckResult for the combined-status probe, or a "not checked" result
        when the preliminary commit lookup fails.
    """
    url = f"{base}/commits/{default_branch}/status"
    try:
        commit = repo.get_commit(default_branch)
    except Exception:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        return CheckResult(
            ok=None,
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
    outcome: ProtectionOutcome,
    base: str,
    web_host: str | None,
) -> CheckResult:
    """Classify the shared branch-protection fetch as Administration: Read.

    A ``Branch not protected`` 404 counts as success: GitHub answered, so the
    token can read the endpoint.

    Returns:
        CheckResult for the branch-protection probe, or a "not checked"
        result when the preliminary branch lookup failed.
    """
    if outcome.stage == "get_branch":
        return CheckResult(
            ok=None,
            value="not checked",
            severity="warning",
            error="branch lookup failed (covered by perm_contents_read)",
        )
    url = f"{base}/branches/{outcome.branch}/protection"
    if outcome.exception is None or is_branch_not_protected(outcome.exception):
        return _classify_permission_response("Administration: Read", 200, url, web_host)
    return _classify_exception(outcome.exception, "Administration: Read", url, web_host)


def run_permission_probes(
    manager: BaseGitHubManager,
    repo: Repository | None,
    *,
    protection_outcome: ProtectionOutcome | None,
) -> dict[str, CheckResult]:
    """Run 6 per-permission read probes; return one CheckResult per probe key.

    When ``repo`` or ``protection_outcome`` is None (repo_accessible.ok=False),
    returns 6 placeholder rows with value="not checked",
    error="repository not accessible" and issues NO PyGithub calls.

    The Administration probe makes no API call; it classifies
    ``protection_outcome``, the branch-protection fetch done by verify_github.

    Returns:
        Mapping from each probe key to its CheckResult.
    """
    if repo is None or protection_outcome is None:
        return {
            k: CheckResult(
                ok=None,
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
        protection_outcome, base, web_host
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
