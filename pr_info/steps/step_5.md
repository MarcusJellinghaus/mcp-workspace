# Step 5 — `UNKNOWN` branch in `_generate_recommendations`

Read `pr_info/steps/summary.md` first for overall context. This step
implements design change (5). Independent of steps 1–4 (only needs the
existing `CIStatus.UNKNOWN` enum member, which already exists).

## Precondition

If `CIStatus` (in `branch_status_rendering.py`) has no `UNKNOWN` member, write
one line to `pr_info/.blocked.txt` and stop.

## WHERE

- `src/mcp_workspace/checks/branch_status.py` (modify `_generate_recommendations` only)
- `tests/checks/test_branch_status_recommendations.py` (modify — add one test)

## WHAT

No signature change to `_generate_recommendations(report_data: Dict[str, Any]) -> List[str]`.

## HOW

No new imports — `CIStatus` is already imported in this module.

Current code:
```python
    elif ci_status == CIStatus.UNAVAILABLE:
        recommendations.append(f"Set a GitHub token ({GITHUB_TOKEN_HINT})")
```
becomes:
```python
    elif ci_status == CIStatus.UNAVAILABLE:
        recommendations.append(f"Set a GitHub token ({GITHUB_TOKEN_HINT})")
    elif ci_status == CIStatus.UNKNOWN:
        recommendations.append("CI status could not be determined — retry")
```

## ALGORITHM

Not applicable — single new `elif` branch in an existing if/elif chain.

## DATA

No new data structures. `report_data["ci_status"] == CIStatus.UNKNOWN` now
yields the recommendation string `"CI status could not be determined — retry"`
instead of falling through to no CI-specific recommendation at all.

## Tests to write first (TDD)

In `tests/checks/test_branch_status_recommendations.py`, add to
`TestGenerateRecommendations`:

```python
def test_ci_unknown(self) -> None:
    recs = _generate_recommendations(
        {
            "ci_status": CIStatus.UNKNOWN,
            "rebase_needed": False,
            "tasks_status": TaskTrackerStatus.COMPLETE,
            "tasks_reason": "All done",
            "tasks_is_blocking": False,
        }
    )
    assert "CI status could not be determined — retry" in recs
    assert "Ready to merge" not in recs
```

Confirm it fails against current code (recommendation absent), then implement
and confirm it passes, alongside the full existing file.

## Commit

One commit: tests + implementation + green checks.
Message: `feat(branch_status): add UNKNOWN recommendation branch`
