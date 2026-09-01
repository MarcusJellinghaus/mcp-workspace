# review-plan review log 1

## Round 1 — 2026-09-01
**Findings**:
I'll gather context first.`pr_info/steps/step_1.md:63` — medium — Gate discards the winner with no debug log; the existing `logger.debug("Detected base branch from merge-base: '%s'")` (`base_branch.py:134`) still fires for a winner that is then rejected, so the only trace of the new behaviour asserts the opposite of what is returned.

`pr_info/steps/step_1.md:151` — medium — Verification lists only the two mock tests in `test_base_branch.py`; `test_parent_branch_detection_git.py:155` (`detect_base_branch(...) == "trunk"`) newly traverses the gate and is the only test covering guard 2's `default is None` path, yet it is not named as a regression guard to check even though `summary.md:46` relies on it.

`pr_info/steps/step_1.md:57` — low — `ls_remote("--heads", "origin", branch_name)` matches any head ending in `/<branch_name>` (e.g. `refs/heads/team/feature-A`), so a same-suffix branch can mask a deletion; `refs/heads/<branch_name>` is the exact pattern.

`pr_info/steps/step_1.md:84` — low — Plan does not instruct updating `_detect_from_merge_base`'s docstring, whose `Returns` still reads "None if not found within threshold" and no longer covers the rejected-winner case.

`pr_info/steps/summary.md:50` — low — Adds a network round trip to `get_base_branch`, which is currently network-free, with no timeout or `GIT_TERMINAL_PROMPT=0`; an origin that demands credentials can block the tool rather than fail into the `None` path.

`pr_info/steps/summary.md:47` — low — "A deeper stack would have elected the nearer live branch" is stated as generally true, but it only holds for a stack; when the rejected winner sat between HEAD and a live non-default branch, falling through to the default branch skips a nearer correct candidate.
**Decisions**:
Verdict(decision='tasks', tasks=['In pr_info/steps/step_1.md, change the remote-existence check to use the exact ref pattern `refs/heads/<branch_name>` in the `ls_remote` call so a same-suffix branch such as `refs/heads/team/feature-A` cannot mask the deletion of `feature-A`.', 'In pr_info/steps/step_1.md, specify the subprocess/environment hardening for the new `ls_remote` call in `get_base_branch`: set `GIT_TERMINAL_PROMPT=0` (and a timeout) so an origin requiring credentials fails into the `None` path instead of blocking the tool.', 'In pr_info/steps/step_1.md, require a debug log on the rejection path so a winner discarded by the gate is traceable, and ensure the existing `logger.debug("Detected base branch from merge-base: \'%s\'")` at base_branch.py:134 does not remain the only trace asserting a result that is not returned.', 'In pr_info/steps/step_1.md, instruct updating `_detect_from_merge_base`\'s docstring `Returns` section, which still reads "None if not found within threshold" and does not cover the newly rejected-winner case.', 'In the Verification section of pr_info/steps/step_1.md, add `test_parent_branch_detection_git.py:155` (`detect_base_branch(...) == "trunk"`) as a regression guard to run, since it is the only existing test exercising guard 2\'s `default is None` path that the new gate now traverses and summary.md:46 depends on it.'], escalate_reason=None)
**Changes**:
applied
