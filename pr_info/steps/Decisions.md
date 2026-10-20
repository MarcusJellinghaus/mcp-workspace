# Decisions — #327 plan corrections (post plan-review escalation)

Logged from the plan-review round that escalated the `on_error` signature
contradiction, and the corrections applied afterward.

| Topic | Decision |
|---|---|
| `on_error` signature | Two-argument: `Callable[[BaseException, T], None]`, called as `on_error(e, resolved)`. Resolves the contradiction between the issue's earlier single-arg text and step_1.md's/step_3.md's two-arg usage. Confirmed with the user; issue #327 updated accordingly before this plan-update round. |
| Error-message formatting | Lives in exactly one place: `_format_error_message(e: BaseException) -> str`, a new private helper added to `base_manager.py` in step 2. `_get_repository()` (step 2) and `ci_results_manager.py`'s `_set_lookup_error` (step 3) both call it instead of each re-deriving the `GithubException`/generic-`Exception` text independently. |
| `GithubException` import in `ci_results_manager.py` | Added via `from mcp_workspace.github_operations.base_manager import GithubException` (step 3), needed for `_set_lookup_error`'s `isinstance` check; was missing from the plan's WHERE/HOW. |
| `# type: ignore[typeddict-item]` comments | Confirmed no change needed — they exist because of the pre-existing `run={}` field, unrelated to `lookup_failed`/`lookup_error`. Step_3.md now states this explicitly rather than leaving issue point 4 silently unaddressed. |
