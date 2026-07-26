"""Task tracker module for parsing TASK_TRACKER.md files.

Provides functions to read, validate, and query task status from
markdown-based task tracker files used in PR workflows.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from enum import Enum


class TaskTrackerError(Exception):
    """Base exception for task tracker errors."""


class TaskTrackerFileNotFoundError(TaskTrackerError):
    """Raised when the TASK_TRACKER.md file is not found."""


class TaskTrackerSectionNotFoundError(TaskTrackerError):
    """Raised when the Tasks section is not found in the tracker."""


class TaskTrackerStatus(str, Enum):
    """Status of the task tracker: COMPLETE, INCOMPLETE, N_A, ERROR."""

    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    N_A = "N_A"
    ERROR = "ERROR"


@dataclass
class TaskInfo:
    """Simple data model for task information."""

    name: str
    is_complete: bool
    line_number: int
    indentation_level: int


TASK_TRACKER_TEMPLATE = """# Task Status Tracker

## Instructions for LLM

This tracks **Feature Implementation** consisting of multiple **Tasks**.

**How to update tasks:**
1. Change [ ] to [x] when implementation step is fully complete (code + checks pass)
2. Change [x] to [ ] if task needs to be reopened
3. Add brief notes in the linked detail files if needed
4. Keep it simple - just GitHub-style checkboxes

**Task format:**
- [x] = Task complete (code + all checks pass)
- [ ] = Task not complete
- Each task links to a detail file in steps/ folder

---

## Tasks

- [ ] Step 1: TODO
- [ ] Step 2: TODO

## Pull Request
"""

# Regex patterns for task matching
_TASK_PATTERN = re.compile(r"^(\s*)- \[([ xX])\] (.+)$")
_TASKS_SECTION_PATTERN = re.compile(r"^##\s+Tasks\s*$")
_SECTION_PATTERN = re.compile(r"^##\s+")


def _read_tracker_file(folder_path: str = "pr_info") -> list[str]:
    """Read TASK_TRACKER.md and return its lines.

    Args:
        folder_path: Path to the folder containing TASK_TRACKER.md.

    Returns:
        List of lines from the file.

    Raises:
        TaskTrackerFileNotFoundError: If the file doesn't exist.
    """
    tracker_path = os.path.join(folder_path, "TASK_TRACKER.md")
    if not os.path.isfile(tracker_path):
        raise TaskTrackerFileNotFoundError(
            f"Task tracker file not found: {tracker_path}"
        )
    with open(tracker_path, encoding="utf-8") as f:
        return f.readlines()


def _find_tasks_section(lines: list[str]) -> int:
    """Find the line index where the Tasks section starts.

    Args:
        lines: Lines from the tracker file.

    Returns:
        Index of the Tasks section header line.

    Raises:
        TaskTrackerSectionNotFoundError: If no Tasks section is found.
    """
    for i, line in enumerate(lines):
        if _TASKS_SECTION_PATTERN.match(line.strip()):
            return i
    raise TaskTrackerSectionNotFoundError(
        "No '## Tasks' section found in TASK_TRACKER.md"
    )


def _parse_tasks(lines: list[str], start_index: int) -> list[TaskInfo]:
    """Parse tasks from lines starting after the Tasks section header.

    Args:
        lines: Lines from the tracker file.
        start_index: Index of the Tasks section header.

    Returns:
        List of TaskInfo objects.
    """
    tasks: list[TaskInfo] = []
    for i in range(start_index + 1, len(lines)):
        line = lines[i]
        # Stop at next section
        if _SECTION_PATTERN.match(line.strip()):
            break
        match = _TASK_PATTERN.match(line.rstrip("\n"))
        if match:
            indent = match.group(1)
            status = match.group(2)
            name = match.group(3).strip()
            # Strip markdown link syntax: [text](url) -> text
            link_match = re.match(r"^\[(.+?)\]\(.+?\)(.*)$", name)
            if link_match:
                name = link_match.group(1) + link_match.group(2)
            tasks.append(
                TaskInfo(
                    name=name.strip(),
                    is_complete=status.lower() == "x",
                    line_number=i + 1,  # 1-based
                    indentation_level=len(indent) // 2,
                )
            )
    return tasks


def _is_meta_task(task_name: str) -> bool:
    """Check if a task name is a meta-task (step-level, not a sub-task).

    Meta tasks are top-level step entries like 'Step 1: ...'
    that contain sub-tasks.

    Returns:
        True if the task name is a step-level meta-task.
    """
    return bool(re.match(r"^Step\s+\d+", task_name))


def get_incomplete_tasks(
    folder_path: str = "pr_info", exclude_meta_tasks: bool = False
) -> list[str]:
    """Get list of incomplete task names from Tasks section.

    Args:
        folder_path: Path to the folder containing TASK_TRACKER.md.
        exclude_meta_tasks: If True, exclude top-level step entries.

    Returns:
        List of incomplete task names.
    """
    lines = _read_tracker_file(folder_path)
    start = _find_tasks_section(lines)
    tasks = _parse_tasks(lines, start)
    incomplete = [t for t in tasks if not t.is_complete]
    if exclude_meta_tasks:
        incomplete = [t for t in incomplete if not _is_meta_task(t.name)]
    return [t.name for t in incomplete]


def has_incomplete_work(folder_path: str = "pr_info") -> bool:
    """Check if there is any incomplete work in the task tracker.

    Args:
        folder_path: Path to the folder containing TASK_TRACKER.md.

    Returns:
        True if there are incomplete tasks.
    """
    return len(get_incomplete_tasks(folder_path)) > 0


def get_task_counts(folder_path: str = "pr_info") -> tuple[int, int]:
    """Get total and completed task counts.

    Args:
        folder_path: Path to the folder containing TASK_TRACKER.md.

    Returns:
        Tuple of (total_tasks, completed_tasks).
    """
    lines = _read_tracker_file(folder_path)
    start = _find_tasks_section(lines)
    tasks = _parse_tasks(lines, start)
    total = len(tasks)
    completed = sum(1 for t in tasks if t.is_complete)
    return (total, completed)


def get_step_progress(
    folder_path: str = "pr_info",
) -> dict[str, dict[str, int | list[str]]]:
    """Get detailed progress info for each step.

    Args:
        folder_path: Path to the folder containing TASK_TRACKER.md.

    Returns:
        Dictionary mapping step names to progress info with keys:
        total, completed, incomplete, incomplete_tasks.
    """
    lines = _read_tracker_file(folder_path)
    start = _find_tasks_section(lines)
    tasks = _parse_tasks(lines, start)

    # Track progress per step using typed intermediate storage
    step_totals: dict[str, int] = {}
    step_completed: dict[str, int] = {}
    step_incomplete: dict[str, int] = {}
    step_incomplete_tasks: dict[str, list[str]] = {}
    step_order: list[str] = []
    current_step: str | None = None

    for task in tasks:
        if task.indentation_level == 0:
            current_step = task.name
            step_order.append(current_step)
            step_totals[current_step] = 0
            step_completed[current_step] = 0
            step_incomplete[current_step] = 0
            step_incomplete_tasks[current_step] = []
        elif current_step is not None:
            step_totals[current_step] += 1
            if task.is_complete:
                step_completed[current_step] += 1
            else:
                step_incomplete[current_step] += 1
                step_incomplete_tasks[current_step].append(task.name)

    # For steps with no sub-tasks, count the step itself
    for step_name in step_order:
        if step_totals[step_name] == 0:
            step_totals[step_name] = 1
            for task in tasks:
                if task.name == step_name and task.indentation_level == 0:
                    if task.is_complete:
                        step_completed[step_name] = 1
                    else:
                        step_incomplete[step_name] = 1
                        step_incomplete_tasks[step_name].append(step_name)
                    break

    steps: dict[str, dict[str, int | list[str]]] = {}
    for step_name in step_order:
        steps[step_name] = {
            "total": step_totals[step_name],
            "completed": step_completed[step_name],
            "incomplete": step_incomplete[step_name],
            "incomplete_tasks": step_incomplete_tasks[step_name],
        }

    return steps


def validate_task_tracker(folder_path: str = "pr_info") -> None:
    """Validate TASK_TRACKER.md has required structure.

    Args:
        folder_path: Path to the folder containing TASK_TRACKER.md.

    Raises:
        TaskTrackerFileNotFoundError: If file doesn't exist.
        TaskTrackerSectionNotFoundError: If Tasks section is missing.
        TaskTrackerError: If no tasks are found.
    """
    lines = _read_tracker_file(folder_path)
    start = _find_tasks_section(lines)
    tasks = _parse_tasks(lines, start)
    if not tasks:
        raise TaskTrackerError("No tasks found in the Tasks section")


def is_task_done(task_name: str, folder_path: str = "pr_info") -> bool:
    """Check if specific task is marked as complete.

    Args:
        task_name: Name of the task to check.
        folder_path: Path to the folder containing TASK_TRACKER.md.

    Returns:
        True if the task is complete.

    Raises:
        TaskTrackerError: If the task is not found.
    """
    lines = _read_tracker_file(folder_path)
    start = _find_tasks_section(lines)
    tasks = _parse_tasks(lines, start)
    for task in tasks:
        if task.name == task_name:
            return task.is_complete
    raise TaskTrackerError(f"Task not found: {task_name}")
