"""Tool group workspace.github: the GitHub tools that write to GitHub."""

import logging
from typing import Annotated, cast

from mcp_coder_utils.log_utils import log_function_call
from mcp_coder_utils.tool_spec import ToolSink, tool_spec
from pydantic import Field

from mcp_workspace.toolset._context import WorkspaceContext
from mcp_workspace.toolset._github_common import (
    issue_manager,
    pr_manager,
    ref_suffix,
    resolve_base_branch,
    tool_error,
)
from mcp_workspace.toolset._github_write_helpers import (
    check_base_branch,
    check_labels,
    edit_change_lines,
    resolve_assignees,
    resolve_body,
    subissue_write,
)

logger = logging.getLogger(__name__)

_BODY_FILE_RULES = "Same path rules as read_file, so gitignored paths are refused."


def _reference_name_text(effect: str) -> str:
    """Describe the reference_name parameter of one write tool.

    Args:
        effect: What happens in the reference project's repository, ending
            right before "that project's GitHub repository".

    Returns:
        The parameter description.
    """
    return (
        f"Optional reference project name. When set, {effect} that project's "
        "GitHub repository instead of the workspace repository."
    )


def register(sink: ToolSink, ctx: WorkspaceContext) -> None:
    """Register the workspace.github tools that write to GitHub, bound to ctx.

    Args:
        sink: Receives one ToolSpec per tool.
        ctx: Settings and state the tools are bound to.
    """

    @log_function_call
    def github_issue_create(
        title: Annotated[
            str, Field(description="Issue title (required, cannot be empty)")
        ],
        body: Annotated[
            str, Field(description="Issue description in Markdown (default: empty)")
        ] = "",
        labels: Annotated[
            list[str] | None,
            Field(
                description=(
                    "Label names to apply — each must already exist in the "
                    "target repository"
                )
            ),
        ] = None,
        assignees: Annotated[
            list[str] | None,
            Field(
                description=(
                    'GitHub usernames to assign; "@me" means the authenticated user'
                )
            ),
        ] = None,
        reference_name: Annotated[
            str | None,
            Field(description=_reference_name_text("the issue is created in")),
        ] = None,
        body_file: Annotated[
            str | None,
            Field(
                description=(
                    "Optional project-relative path whose content is sent as the "
                    "body, byte for byte (a leading UTF-8 BOM is dropped). "
                    f"{_BODY_FILE_RULES} Mutually exclusive with a non-empty "
                    "body. The title is never read from the file; the Base "
                    "Branch check applies to the file text."
                )
            ),
        ] = None,
    ) -> str:
        """Create a real GitHub issue. This writes to GitHub.

        Targets the workspace repository, or a reference project's repository when
        reference_name is given. Workflow status labels (status-*) are rejected —
        use `github_issue_set_status`. Other label names are validated against
        the target repository's labels before writing, so a typo cannot silently
        create a new label. A malformed `### Base Branch` section (more than one
        line) is rejected before any write, unless the server was started with
        `--no-enforce-base-branch-format`.

        Returns:
            "Created issue #<number> — <url>" followed by the resulting labels and
            assignees, or error message string.
        """
        try:
            body = cast(str, resolve_body(ctx, body, body_file, conflict=bool(body)))
            body_error = check_base_branch(ctx, body)
            if body_error:
                return body_error
            manager = issue_manager(ctx, reference_name)
            label_error = check_labels(manager, labels or [], [], reference_name)
            if label_error:
                return label_error
            resolved = resolve_assignees(manager, assignees or [])
            issue = manager.create_issue(
                title=title,
                body=body,
                labels=labels,
                assignees=resolved or None,
            )
            # Empty IssueData is the library's swallowed-failure sentinel
            if not issue["number"]:
                return (
                    "Error: issue creation failed - no issue was created"
                    f"{ref_suffix(reference_name)}"
                )
            # GitHub drops a non-assignable login or an unusable label silently, so
            # the resulting lists are the only way a caller sees what did not take
            return (
                f"Created issue #{issue['number']} — {issue['url']}\n"
                f"Labels: {', '.join(issue['labels']) or '(none)'}\n"
                f"Assignees: {', '.join(issue['assignees']) or '(none)'}"
            )
        except Exception as e:
            return tool_error(e)

    @log_function_call
    def github_issue_edit(
        number: Annotated[
            int, Field(description="Issue number to edit (must be positive)")
        ],
        title: Annotated[
            str | None,
            Field(description="New issue title; surrounding whitespace is stripped"),
        ] = None,
        body: Annotated[
            str | None, Field(description="New issue description in Markdown")
        ] = None,
        add_labels: Annotated[
            list[str] | None,
            Field(
                description=(
                    "Label names to add — each must already exist in the target "
                    "repository"
                )
            ),
        ] = None,
        remove_labels: Annotated[
            list[str] | None,
            Field(
                description="Label names to remove; labels already absent are ignored"
            ),
        ] = None,
        add_assignees: Annotated[
            list[str] | None,
            Field(
                description='Usernames to assign; "@me" means the authenticated user'
            ),
        ] = None,
        state: Annotated[
            str | None,
            Field(description='New issue state — only "open" or "closed" are accepted'),
        ] = None,
        reference_name: Annotated[
            str | None,
            Field(description=_reference_name_text("the issue is edited in")),
        ] = None,
        body_file: Annotated[
            str | None,
            Field(
                description=(
                    "Optional project-relative path whose content becomes the new "
                    "body, byte for byte (a leading UTF-8 BOM is dropped). "
                    f"{_BODY_FILE_RULES} Mutually exclusive with body — any body "
                    'value, including "", conflicts.'
                )
            ),
        ] = None,
    ) -> str:
        """Modify a real GitHub issue. This writes to GitHub.

        Targets the workspace repository, or a reference project's repository when
        reference_name is given. Only the arguments you pass are changed. Label
        changes are additive and subtractive, never a replacement of the whole set.
        Workflow status labels (status-*) are rejected on the add and the remove
        side — use `github_issue_set_status`. When `body` or `body_file` is
        passed, a malformed `### Base Branch` section (more than one line) is
        rejected before any write, unless the server was started with
        `--no-enforce-base-branch-format`.

        The edit is not a transaction: if a later part fails, the earlier part
        stays applied. The result then opens with a warning naming which requested
        changes landed, followed by the resulting state. A failure that happens
        before any write instead opens with an error saying nothing was applied.

        Returns:
            "Updated issue #<number> — <url> (state: <state>)" followed by the
            resulting labels and assignees. When nothing was applied, the same
            block opens with an error line and reads "Issue #<number> — ..."
            instead of "Updated issue". Or error message string.
        """
        # Lazy imports: keep PyGithub off the server startup import path
        from mcp_workspace.github_operations import (
            GithubException,
            RetryError,
            format_rate_limit_error,
        )
        from mcp_workspace.github_operations.issues.types import (
            create_empty_issue_data,
        )

        try:
            # Pre-write validation. Nothing has been written yet, so a plain error
            # is honest — and it keeps the inner except below meaning exactly one
            # thing: the write sequence started and something after it failed.
            body = resolve_body(ctx, body, body_file, conflict=body is not None)
            if number <= 0:
                return f"Error: invalid issue number: {number}"
            if title is not None and not title.strip():
                return "Error: Issue title cannot be empty"
            if state not in (None, "open", "closed"):
                return f"Error: state must be 'open' or 'closed', got: {state}"
            body_error = check_base_branch(ctx, body)
            if body_error:
                return body_error

            manager = issue_manager(ctx, reference_name)
            label_error = check_labels(
                manager, add_labels or [], remove_labels or [], reference_name
            )
            if label_error:
                return label_error
            resolved = resolve_assignees(manager, add_assignees or [])

            reason = ""
            # edit_issue appends one entry per write call it issues, before
            # issuing it. Empty therefore means no write was ever issued — the
            # failure came before the first one, or the request had no write to
            # make. Either way nothing can have been written, which is the only
            # case in which claiming "no changes were made" is honest.
            attempted: list[str] = []
            try:
                issue = manager.edit_issue(
                    number,
                    title=title,
                    body=body,
                    add_labels=add_labels,
                    remove_labels=remove_labels,
                    add_assignees=resolved or None,
                    state=state,
                    attempted_writes=attempted,
                )
                # Empty IssueData is the library's swallowed-failure sentinel
                if not issue["number"]:
                    reason = "swallowed API error"
            except (GithubException, RetryError, ValueError) as exc:
                # _handle_github_errors re-raises 401/403, rate limits and every
                # ValueError, including the identity check on edit_issue's own
                # closing refetch. All can happen after part of the write landed.
                issue = create_empty_issue_data()
                reason = format_rate_limit_error(exc) or str(exc)

            if reason:
                # The write sequence may have started and did not finish cleanly —
                # read the issue back so the caller learns what actually landed.
                reread_error = ""
                try:
                    issue = manager.get_issue(number)
                except Exception as exc:
                    issue = create_empty_issue_data()
                    reread_error = f": {format_rate_limit_error(exc) or exc}"
                if not issue["number"]:
                    if not attempted:
                        return (
                            f"Error: issue #{number} not found or not accessible"
                            f"{ref_suffix(reference_name)} "
                            f"({reason}){reread_error} - no changes were made"
                        )
                    return (
                        f"Error: edit of issue #{number} failed"
                        f"{ref_suffix(reference_name)} ({reason}) and the "
                        f"issue could not be re-read{reread_error} - these changes "
                        f"may or may not have been applied: {', '.join(attempted)}"
                    )

            # Same signal as above: an empty write log means no write went out, so
            # nothing was applied — which makes both "partially failed" and
            # "Updated" untrue.
            failed_before_write = bool(reason) and not attempted
            lines: list[str] = []
            if failed_before_write:
                lines.append(
                    f"Error: edit of issue #{number} failed ({reason}) "
                    f"- no changes were made; current state below"
                )
            elif reason:
                lines.append(
                    f"Warning: edit partially failed ({reason}) — resulting state below"
                )
                lines.extend(
                    edit_change_lines(
                        issue, title, body, state, add_labels, remove_labels, resolved
                    )
                )
            state_verb = "Issue" if failed_before_write else "Updated issue"
            lines.append(
                f"{state_verb} #{issue['number']} — {issue['url']} "
                f"(state: {issue['state']})"
            )
            lines.append(f"Labels: {', '.join(issue['labels']) or '(none)'}")
            lines.append(f"Assignees: {', '.join(issue['assignees']) or '(none)'}")
            return "\n".join(lines)
        except Exception as e:
            return tool_error(e)

    @log_function_call
    def github_issue_set_status(
        number: Annotated[int, Field(description="Issue number.")],
        status: Annotated[
            str,
            Field(description='Target status label, e.g. "status-01:created".'),
        ],
        from_status: Annotated[
            str | None,
            Field(
                description=(
                    "Optional guard. When set, the status is changed only if the "
                    "issue's sole current status label is this one; otherwise "
                    "nothing is written."
                )
            ),
        ] = None,
        reference_name: Annotated[
            str | None,
            Field(description=_reference_name_text("the issue is changed in")),
        ] = None,
        refresh_labels: Annotated[
            bool, Field(description="Force a reload of the label cache from GitHub.")
        ] = False,
    ) -> str:
        """Set the workflow status label of a real GitHub issue. This writes to GitHub.

        Targets the workspace repository, or a reference project's repository when
        reference_name is given — no local clone is needed. ``status`` and
        ``from_status`` are full ``status-*`` label names that must already exist
        in the target repository, matched case-insensitively; list them with
        ``github_label_list(search="status-")``. Every other ``status-*`` label on
        the issue is removed; other labels are kept. Pull requests are rejected;
        closed issues are allowed. A status change can start workflow automation
        in the target repository.

        Valid status labels come from a disk cache shared across sessions, kept for
        up to 24 h; pass ``refresh_labels=True`` to reload it when a newly created
        label is reported as not found.

        Returns:
            The old and new status with the resulting labels, a no-op or guard
            message, the available status labels when a label is not found, or
            error message string.
        """
        # Lazy import: keeps PyGithub off the server startup import path
        from mcp_workspace.github_operations.issues.status import set_issue_status

        try:
            return set_issue_status(
                issue_manager(ctx, reference_name),
                number,
                status,
                from_status,
                refresh_labels,
            )
        except Exception as e:
            return tool_error(e)

    @log_function_call
    def github_subissue_add(
        parent_number: Annotated[
            int, Field(description="Parent issue number (must be positive)")
        ],
        child_number: Annotated[
            int,
            Field(
                description=(
                    "Issue number to link under the parent (must be positive and "
                    "differ from parent_number)"
                )
            ),
        ],
        reference_name: Annotated[
            str | None,
            Field(description=_reference_name_text("both issues are in")),
        ] = None,
    ) -> str:
        """Link an existing issue as a sub-issue of another. This writes to GitHub.

        Both issues live in the same repository: the workspace repository, or the
        reference project's repository when reference_name is given — it scopes
        both numbers. GitHub rejects a child that already has a parent, here or
        elsewhere, with one generic message; call github_subissue_list first if
        the difference matters.

        Returns:
            "Linked #<child> as a sub-issue of #<parent> — <url> (~<N> sub-issues,
            may lag)", or error message string. The count is approximate and
            omitted when it could not be read. Call github_subissue_list for the
            exact set.
        """
        return subissue_write(ctx, parent_number, child_number, False, reference_name)

    @log_function_call
    def github_subissue_remove(
        parent_number: Annotated[
            int, Field(description="Parent issue number (must be positive)")
        ],
        child_number: Annotated[
            int,
            Field(
                description=(
                    "Issue number to unlink from the parent (must be positive and "
                    "differ from parent_number)"
                )
            ),
        ],
        reference_name: Annotated[
            str | None,
            Field(description=_reference_name_text("both issues are in")),
        ] = None,
    ) -> str:
        """Unlink a sub-issue from its parent. This writes to GitHub.

        Both issues live in the same repository: the workspace repository, or the
        reference project's repository when reference_name is given — it scopes
        both numbers. Removing a child that is not linked to the parent is an
        error, not a silent no-op.

        Returns:
            "Unlinked #<child> from #<parent> — <url> (~<N> sub-issues, may lag)",
            or error message string. The count is approximate and omitted when it
            could not be read. Call github_subissue_list for the exact set.
        """
        return subissue_write(ctx, parent_number, child_number, True, reference_name)

    @log_function_call
    def github_issue_comment(
        number: Annotated[
            int, Field(description="Issue number to comment on (must be positive)")
        ],
        body: Annotated[
            str,
            Field(
                description=(
                    "Comment text in Markdown (cannot be empty when body_file is "
                    "not given)"
                )
            ),
        ] = "",
        reference_name: Annotated[
            str | None,
            Field(description=_reference_name_text("the comment is posted to")),
        ] = None,
        body_file: Annotated[
            str | None,
            Field(
                description=(
                    "Optional project-relative path whose content becomes the "
                    "comment text (a leading UTF-8 BOM is dropped). "
                    f"{_BODY_FILE_RULES} Mutually exclusive with a non-empty body."
                )
            ),
        ] = None,
    ) -> str:
        """Post a real comment on a GitHub issue. This writes to GitHub.

        Pass the comment text as `body` or `body_file` — exactly one. Multi-line
        Markdown is sent through unchanged, except that leading and trailing
        whitespace is stripped.

        Returns:
            "Added comment to issue #<number> — <url>", or error message string.
        """
        try:
            body = cast(str, resolve_body(ctx, body, body_file, conflict=bool(body)))
            if not body:
                if body_file is not None:
                    return f"Error: body_file '{body_file}' is empty"
                return "Error: pass body or body_file"
            manager = issue_manager(ctx, reference_name)
            comment = manager.add_comment(number, body)
            # Empty CommentData carries id == 0, not number == 0 as issues do
            if not comment["id"]:
                return (
                    f"Error: failed to add comment to issue #{number}"
                    f"{ref_suffix(reference_name)}"
                )
            return f"Added comment to issue #{number} — {comment['url']}"
        except Exception as e:
            return tool_error(e)

    @log_function_call
    def github_review_comment_reply(
        pr_number: Annotated[
            int,
            Field(
                description=(
                    "Pull request number the review comment belongs to (must be "
                    "positive)"
                )
            ),
        ],
        comment_id: Annotated[
            int, Field(description="Review comment ID to reply to (must be positive)")
        ],
        body: Annotated[
            str, Field(description="Reply text in Markdown (required, cannot be empty)")
        ],
        reference_name: Annotated[
            str | None,
            Field(description=_reference_name_text("the reply is posted to")),
        ] = None,
    ) -> str:
        """Reply to an inline PR review comment. This writes to GitHub.

        Returns:
            "Replied to review comment <comment_id> on PR #<pr_number> — <url>", or
            error message string.
        """
        try:
            manager = pr_manager(ctx, reference_name)
            reply = manager.reply_to_review_comment(pr_number, comment_id, body)
            # Empty CommentData carries id == 0, not number == 0 as issues do
            if not reply["id"]:
                return (
                    f"Error: failed to reply to review comment {comment_id} "
                    f"on PR #{pr_number}{ref_suffix(reference_name)}"
                )
            return (
                f"Replied to review comment {comment_id} on PR #{pr_number} — "
                f"{reply['url']}"
            )
        except Exception as e:
            return tool_error(e)

    @log_function_call
    def github_review_thread_resolve(
        pr_number: Annotated[
            int,
            Field(
                description=(
                    "Pull request number the review thread belongs to (must be "
                    "positive)"
                )
            ),
        ],
        thread_id: Annotated[
            str, Field(description="GraphQL node ID of the review thread to resolve")
        ],
        reference_name: Annotated[
            str | None,
            Field(description=_reference_name_text("the thread is resolved on")),
        ] = None,
    ) -> str:
        """Resolve an inline PR review thread. This writes to GitHub.

        Returns:
            "Resolved review thread <thread_id> on PR #<pr_number>", or error
            message string.
        """
        try:
            manager = pr_manager(ctx, reference_name)
            resolved = manager.resolve_review_thread(pr_number, thread_id)
            if not resolved:
                return (
                    f"Error: failed to resolve review thread {thread_id} "
                    f"on PR #{pr_number}{ref_suffix(reference_name)}"
                )
            return (
                f"Resolved review thread {thread_id} on PR #{pr_number}"
                f"{ref_suffix(reference_name)}"
            )
        except Exception as e:
            return tool_error(e)

    @log_function_call
    def github_pr_create(
        title: Annotated[
            str, Field(description="Pull request title (required, cannot be empty)")
        ],
        body: Annotated[
            str,
            Field(description="Pull request description in Markdown (default: empty)"),
        ] = "",
        head: Annotated[
            str | None,
            Field(
                description="Source branch (default: the currently checked-out branch)"
            ),
        ] = None,
        base: Annotated[
            str | None,
            Field(
                description=(
                    "Target branch (default: resolved for head — the issue's Base "
                    "Branch, an open PR's base, the merge-base parent, or the "
                    "default branch — and verified on origin)"
                )
            ),
        ] = None,
        body_file: Annotated[
            str | None,
            Field(
                description=(
                    "Optional project-relative path whose content becomes the "
                    "description (a leading UTF-8 BOM is dropped). "
                    f"{_BODY_FILE_RULES} Mutually exclusive with a non-empty body."
                )
            ),
        ] = None,
    ) -> str:
        """Open a real pull request on this repository. This writes to GitHub.

        Returns:
            "Created PR #<number> — <url>", or an error message string. Passing
            both body and body_file, or a body_file that cannot be read or is
            refused, is returned as an error without creating anything. When base
            is omitted, these errors are also returned without creating anything:
            "Error: issue #N: <sentence>" (malformed Base Branch section),
            "Error: could not determine base branch for <head>",
            "Error: base branch '<base>' not found on origin",
            "Error: could not verify base branch '<base>' on origin: <cause>".
        """
        # Lazy imports: keep PyGithub/GitPython off the server startup import path
        from mcp_workspace.git_operations import (
            get_current_branch_name,
            probe_origin_branch,
        )
        from mcp_workspace.github_operations.pr_manager import PullRequestManager

        try:
            body = cast(str, resolve_body(ctx, body, body_file, conflict=bool(body)))
            if not title.strip():
                return "Error: PR title cannot be empty"
            project_dir = ctx.project_dir
            manager = PullRequestManager(project_dir=project_dir)
            head = head or get_current_branch_name(project_dir)
            if not head:
                return "Error: could not determine the current branch for head"
            if not base:
                base, error = resolve_base_branch(project_dir, head, manager)
                if error:
                    return error
                if not base:
                    return f"Error: could not determine base branch for {head}"
                try:
                    probe = probe_origin_branch(project_dir, base)
                except Exception as e:  # pylint: disable=broad-exception-caught
                    return (
                        f"Error: could not verify base branch '{base}' on origin: {e}"
                    )
                if probe["exists"] is None:
                    cause = probe["stderr"] or probe["error"]
                    return (
                        f"Error: could not verify base branch '{base}' on origin: "
                        f"{cause}"
                    )
                if not probe["exists"]:
                    return f"Error: base branch '{base}' not found on origin"
            if head == base:
                return f"Error: head and base are the same branch ({head})"
            for name in (head, base):
                # Reuse the library's branch rules rather than restating them
                # pylint: disable-next=protected-access
                if not manager._validate_branch_name(name):
                    return f"Error: invalid branch name: {name}"
            pr = manager.create_pull_request(
                title=title,
                head_branch=head,
                base_branch=base,
                body=body,
            )
            # create_pull_request's swallowed-failure sentinel is {}, not number == 0
            if not pr.get("number"):
                return "Error: PR creation failed - no pull request was created"
            return f"Created PR #{pr['number']} — {pr['url']}"
        except Exception as e:
            return tool_error(e)

    for fn in (
        github_issue_create,
        github_issue_edit,
        github_issue_set_status,
        github_subissue_add,
        github_subissue_remove,
        github_issue_comment,
        github_review_comment_reply,
        github_review_thread_resolve,
        github_pr_create,
    ):
        sink.add(tool_spec(fn, group="workspace.github", read_only=False))
