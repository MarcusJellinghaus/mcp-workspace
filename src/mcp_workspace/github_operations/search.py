"""GitHub issue-search query construction and argument validation.

Two-phase by design: from_arguments validates without needing a repository,
to_query assembles once the repository is known. The handler in server.py can
therefore reject bad input before paying for a network round-trip.
"""

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class SearchSpec:
    """Validated, normalized arguments for one GitHub issue search.

    Obtain instances through :meth:`from_arguments` only - that is what
    guarantees a query is never built from unvalidated input.

    Attributes:
        query: Caller's raw query text, sent through unmodified.
        state: Lower-cased "open", "closed", "all", or None.
        labels: Label names, never None.
        assignee: Assignee username, or None when unset or empty.
        needs_type_default: True when the query names no result type, so
            "is:issue" must be added.
        has_inline_state: True when the query already names a state inline.
    """

    query: str
    state: Optional[str]
    labels: list[str]
    assignee: Optional[str]
    needs_type_default: bool
    has_inline_state: bool

    @classmethod
    def from_arguments(
        cls,
        query: str,
        state: Optional[str] = None,
        labels: Optional[list[str]] = None,
        assignee: Optional[str] = None,
    ) -> "SearchSpec":
        """Validate and normalize search arguments.

        Args:
            query: Search query text.
            state: "open", "closed" or "all", matched case-insensitively.
            labels: Label names to AND together.
            assignee: Assignee username.

        Returns:
            A SearchSpec with normalized values and precomputed flags.

        Raises:
            ValueError: If state, query, a label or assignee is invalid. The
                message carries no "Error: " prefix - the MCP handler adds it.
        """
        # Case-insensitive, matching every inline qualifier check below
        normalized_state = state.lower() if state else None
        if normalized_state and normalized_state not in ("open", "closed", "all"):
            raise ValueError(
                f"Invalid state: {state}. Expected 'open', 'closed' or 'all'."
            )
        # Reject rather than forward: live probing shows GitHub matches nothing
        # against "type:pull-request", so sending it on would return an empty
        # result indistinguishable from a genuine one.
        if re.search(r"(?:^|\s)type:pull-request(?![\w-])", query, re.IGNORECASE):
            raise ValueError(
                "Invalid qualifier 'type:pull-request': "
                "use 'is:pull-request' or 'is:pr'"
            )
        # GitHub search has no documented escape inside a quoted qualifier, so a
        # label carrying a double quote cannot be expressed - fail loudly instead
        # of guessing at an escape and silently matching something else. An empty
        # or whitespace-only label is unrepresentable for the same reason: it goes
        # out as label:"" and matches nothing, which reads as a genuine result.
        for label in labels or []:
            if not label.strip():
                raise ValueError(
                    f"Invalid label {label!r}: "
                    "a label cannot be empty or whitespace-only"
                )
            if '"' in label:
                raise ValueError(
                    f"Invalid label {label!r}: "
                    "a label containing a double quote cannot be searched"
                )
        # Unquoted in the query, so whitespace would split into "assignee:john"
        # plus a stray free-text term - a silently narrower search, not an error.
        if assignee and any(char.isspace() for char in assignee):
            raise ValueError(
                f"Invalid assignee {assignee!r}: "
                "a GitHub username cannot contain whitespace"
            )
        return cls(
            query=query,
            state=normalized_state,
            labels=list(labels or []),
            assignee=assignee or None,
            # GitHub's /search/issues rejects a query that names no result type.
            # "type:pull-request" is deliberately absent - it is rejected above.
            needs_type_default=not re.search(
                r"(?:^|\s)(?:is:(?:issue|pr|pull-request)|type:(?:issue|pr))(?![\w-])",
                query,
                re.IGNORECASE,
            ),
            # An inline state qualifier wins: adding the parameter's on top would
            # send "is:closed is:open", which GitHub matches nothing against.
            # Both spellings are live-verified to filter by state - see
            # test_github_search_live_state_spelling_honored - so trusting the
            # "state:" form here cannot silently drop the caller's state filter.
            has_inline_state=bool(
                re.search(
                    r"(?:^|\s)(?:is|state):(?:open|closed)(?![\w-])",
                    query,
                    re.IGNORECASE,
                )
            ),
        )

    def to_query(self, repo_full_name: str) -> str:
        """Assemble the GitHub search query string.

        Args:
            repo_full_name: Repository in "owner/repo" form.

        Returns:
            The complete query string, repo-scoped.
        """
        parts = [f"repo:{repo_full_name}"]
        if self.needs_type_default:
            parts.append("is:issue")
        parts.append(self.query)
        if self.state in ("open", "closed") and not self.has_inline_state:
            parts.append(f"is:{self.state}")
        for label in self.labels:
            # Always quoted - this repo's own labels contain colons
            parts.append(f'label:"{label}"')
        if self.assignee:
            parts.append(f"assignee:{self.assignee}")
        # `if p` drops an empty query, so no double or trailing space
        return " ".join(p for p in parts if p)
