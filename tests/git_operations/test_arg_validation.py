"""Tests for git argument validation against per-command allowlists."""

import pytest

from mcp_workspace.git_operations.arg_validation import (
    split_args_pathspec,
    validate_args,
    validate_branch_has_read_flag,
)


class TestValidateArgsLogAllowed:
    """Allowed log flags pass through silently."""

    def test_oneline(self) -> None:
        validate_args("log", ["--oneline"])

    def test_format_with_value(self) -> None:
        validate_args("log", ["--format=short"])

    def test_short_n_with_value(self) -> None:
        validate_args("log", ["-n5"])

    def test_grep(self) -> None:
        validate_args("log", ["--grep", "fix"])

    def test_multiple_flags(self) -> None:
        validate_args("log", ["--oneline", "--graph", "--all", "-n10"])


class TestValidateArgsDiffAllowed:
    """Allowed diff flags pass through silently."""

    def test_staged(self) -> None:
        validate_args("diff", ["--staged"])

    def test_cached(self) -> None:
        validate_args("diff", ["--cached"])

    def test_rename_detection(self) -> None:
        validate_args("diff", ["-M"])

    def test_unified_with_value(self) -> None:
        validate_args("diff", ["--unified=3"])

    def test_diff_algorithm_equals(self) -> None:
        validate_args("diff", ["--diff-algorithm=patience"])


class TestValidateArgsStatusAllowed:
    """Allowed status flags pass through silently."""

    def test_short(self) -> None:
        validate_args("status", ["--short"])

    def test_short_alias(self) -> None:
        validate_args("status", ["-s"])

    def test_branch_short(self) -> None:
        validate_args("status", ["-b"])

    def test_porcelain(self) -> None:
        validate_args("status", ["--porcelain"])


class TestValidateArgsMergeBaseAllowed:
    """Allowed merge-base flags pass through silently."""

    def test_all(self) -> None:
        validate_args("merge_base", ["--all"])

    def test_is_ancestor(self) -> None:
        validate_args("merge_base", ["--is-ancestor"])

    def test_fork_point(self) -> None:
        validate_args("merge_base", ["--fork-point"])


class TestValidateArgsRefsPassThrough:
    """Non-flag args (refs, SHAs, ranges) pass through without validation."""

    def test_branch_name(self) -> None:
        validate_args("log", ["main"])

    def test_sha(self) -> None:
        validate_args("log", ["abc1234"])

    def test_range(self) -> None:
        validate_args("log", ["main..HEAD"])

    def test_remote_ref(self) -> None:
        validate_args("diff", ["origin/main"])

    def test_empty_args(self) -> None:
        validate_args("log", [])


class TestValidateArgsRejected:
    """Unknown or dangerous flags raise ValueError."""

    def test_rejects_unknown_flag(self) -> None:
        with pytest.raises(ValueError, match="--output"):
            validate_args("log", ["--output"])

    def test_rejects_exec_flag(self) -> None:
        with pytest.raises(ValueError, match="--exec"):
            validate_args("diff", ["--exec"])

    def test_rejects_double_dash(self) -> None:
        with pytest.raises(ValueError, match="merge_base does not accept"):
            validate_args("merge_base", ["--"])

    def test_error_message_contains_command(self) -> None:
        with pytest.raises(ValueError, match="git_log"):
            validate_args("log", ["--unknown"])

    def test_error_message_contains_github_url(self) -> None:
        with pytest.raises(ValueError, match="github.com"):
            validate_args("log", ["--unknown"])


class TestValidateArgsFetchAllowed:
    """Allowed fetch flags pass through silently."""

    def test_prune(self) -> None:
        validate_args("fetch", ["--prune"])

    def test_tags(self) -> None:
        validate_args("fetch", ["--tags"])

    def test_verbose(self) -> None:
        validate_args("fetch", ["--verbose"])

    def test_depth_with_value(self) -> None:
        validate_args("fetch", ["--depth=1"])


class TestValidateArgsShowAllowed:
    """Allowed show flags pass through silently."""

    def test_format(self) -> None:
        validate_args("show", ["--format=short"])

    def test_stat(self) -> None:
        validate_args("show", ["--stat"])

    def test_oneline(self) -> None:
        validate_args("show", ["--oneline"])

    def test_patch(self) -> None:
        validate_args("show", ["-p"])


class TestValidateArgsBranchAllowed:
    """Allowed branch flags pass through silently."""

    def test_list(self) -> None:
        validate_args("branch", ["--list"])

    def test_all(self) -> None:
        validate_args("branch", ["-a"])

    def test_remote(self) -> None:
        validate_args("branch", ["-r"])

    def test_contains(self) -> None:
        validate_args("branch", ["--contains"])

    def test_show_current(self) -> None:
        validate_args("branch", ["--show-current"])


class TestValidateArgsRevParseAllowed:
    """Allowed rev-parse flags pass through silently."""

    def test_abbrev_ref(self) -> None:
        validate_args("rev_parse", ["--abbrev-ref"])

    def test_show_toplevel(self) -> None:
        validate_args("rev_parse", ["--show-toplevel"])

    def test_verify(self) -> None:
        validate_args("rev_parse", ["--verify"])


class TestValidateArgsLsTreeAllowed:
    """Allowed ls-tree flags pass through silently."""

    def test_recursive(self) -> None:
        validate_args("ls_tree", ["-r"])

    def test_name_only(self) -> None:
        validate_args("ls_tree", ["--name-only"])

    def test_long(self) -> None:
        validate_args("ls_tree", ["--long"])


class TestValidateArgsLsFilesAllowed:
    """Allowed ls-files flags pass through silently."""

    def test_cached(self) -> None:
        validate_args("ls_files", ["--cached"])

    def test_others(self) -> None:
        validate_args("ls_files", ["--others"])

    def test_exclude_standard(self) -> None:
        validate_args("ls_files", ["--exclude-standard"])


class TestValidateArgsLsRemoteAllowed:
    """Allowed ls-remote flags pass through silently."""

    def test_heads(self) -> None:
        validate_args("ls_remote", ["--heads"])

    def test_tags(self) -> None:
        validate_args("ls_remote", ["--tags"])

    def test_get_url(self) -> None:
        validate_args("ls_remote", ["--get-url"])


class TestValidateArgsCrossCommandIsolation:
    """Flags valid for one command must not work in another."""

    def test_staged_rejected_in_log(self) -> None:
        with pytest.raises(ValueError, match="--staged"):
            validate_args("log", ["--staged"])

    def test_graph_rejected_in_diff(self) -> None:
        with pytest.raises(ValueError, match="--graph"):
            validate_args("diff", ["--graph"])

    def test_porcelain_rejected_in_merge_base(self) -> None:
        with pytest.raises(ValueError, match="--porcelain"):
            validate_args("merge_base", ["--porcelain"])

    def test_prune_rejected_in_show(self) -> None:
        with pytest.raises(ValueError, match="--prune"):
            validate_args("show", ["--prune"])

    def test_cached_rejected_in_branch(self) -> None:
        with pytest.raises(ValueError, match="--cached"):
            validate_args("branch", ["--cached"])

    def test_heads_rejected_in_ls_files(self) -> None:
        with pytest.raises(ValueError, match="--heads"):
            validate_args("ls_files", ["--heads"])


class TestValidateBranchHasReadFlag:
    """validate_branch_has_read_flag rejects bare args, accepts read-only flags."""

    def test_bare_args_rejected(self) -> None:
        with pytest.raises(ValueError, match="read-only flag"):
            validate_branch_has_read_flag(["new-branch"])

    def test_empty_args_rejected(self) -> None:
        with pytest.raises(ValueError, match="read-only flag"):
            validate_branch_has_read_flag([])

    def test_list_passes(self) -> None:
        validate_branch_has_read_flag(["--list"])

    def test_all_passes(self) -> None:
        validate_branch_has_read_flag(["-a"])

    def test_show_current_passes(self) -> None:
        validate_branch_has_read_flag(["--show-current"])

    def test_verbose_passes(self) -> None:
        validate_branch_has_read_flag(["-v"])

    def test_sort_with_value_passes(self) -> None:
        validate_branch_has_read_flag(["--sort=committerdate"])


class TestValidateArgsUnknownCommand:
    """Unknown commands raise ValueError."""

    def test_push_rejected(self) -> None:
        with pytest.raises(ValueError, match="push"):
            validate_args("push", [])

    def test_reset_rejected(self) -> None:
        with pytest.raises(ValueError, match="reset"):
            validate_args("reset", ["--hard"])


class TestValidateArgsFlagEqualsValue:
    """Flags with = values are matched by prefix."""

    def test_format_equals_oneline(self) -> None:
        validate_args("log", ["--format=oneline"])

    def test_diff_algorithm_equals_patience(self) -> None:
        validate_args("diff", ["--diff-algorithm=patience"])

    def test_date_equals_relative(self) -> None:
        validate_args("log", ["--date=relative"])


class TestValidateArgsShortFlagWithValue:
    """Short flags with attached values matched by 2-char prefix."""

    def test_n5(self) -> None:
        validate_args("log", ["-n5"])

    def test_u3(self) -> None:
        validate_args("diff", ["-U3"])

    def test_short_untracked(self) -> None:
        validate_args("status", ["-u"])


class TestValidateArgsNumericFlags:
    """Bare numeric flags like -10 are allowed for opted-in commands."""

    def test_log_numeric_flag(self) -> None:
        validate_args("log", ["--oneline", "-10"])

    def test_show_numeric_flag(self) -> None:
        validate_args("show", ["-3"])

    def test_diff_numeric_flag(self) -> None:
        validate_args("diff", ["-5"])

    def test_log_numeric_zero(self) -> None:
        validate_args("log", ["-0"])

    def test_status_rejects_numeric_flag(self) -> None:
        with pytest.raises(ValueError, match="-10"):
            validate_args("status", ["-10"])

    def test_branch_rejects_numeric_flag(self) -> None:
        with pytest.raises(ValueError, match="-5"):
            validate_args("branch", ["-5"])

    def test_non_numeric_flag_still_rejected(self) -> None:
        with pytest.raises(ValueError, match="-abc"):
            validate_args("log", ["-abc"])

    def test_mixed_alphanumeric_flag_rejected(self) -> None:
        with pytest.raises(ValueError, match="-12abc"):
            validate_args("log", ["-12abc"])


class TestSplitArgsPathspec:
    """split_args_pathspec splits args on '--' for pathspec commands."""

    def test_no_op_for_non_pathspec_command(self) -> None:
        assert split_args_pathspec("merge_base", ["--", "x"], None) == (
            ["--", "x"],
            None,
        )

    def test_no_op_when_no_double_dash(self) -> None:
        assert split_args_pathspec("log", ["--oneline"], None) == (
            ["--oneline"],
            None,
        )

    def test_split_with_one_path(self) -> None:
        assert split_args_pathspec("diff", ["main", "--", "README.md"], None) == (
            ["main"],
            ["README.md"],
        )

    def test_split_with_multiple_paths(self) -> None:
        assert split_args_pathspec("log", ["--", "a.py", "b.py"], None) == (
            [],
            ["a.py", "b.py"],
        )

    def test_empty_tail_is_noop(self) -> None:
        assert split_args_pathspec("log", ["--"], None) == ([], None)

    def test_empty_tail_preserves_explicit_pathspec(self) -> None:
        assert split_args_pathspec("log", ["--"], ["x"]) == ([], ["x"])

    def test_multiple_double_dash_rejected(self) -> None:
        with pytest.raises(ValueError, match="Multiple '--'"):
            split_args_pathspec("diff", ["--", "a", "--", "b"], None)

    def test_conflict_with_explicit_pathspec_rejected(self) -> None:
        with pytest.raises(ValueError, match="either '--' in args or the 'pathspec'"):
            split_args_pathspec("diff", ["--", "x"], ["y"])

    def test_preserves_pathspec_when_no_double_dash(self) -> None:
        assert split_args_pathspec("log", ["main"], ["README.md"]) == (
            ["main"],
            ["README.md"],
        )
