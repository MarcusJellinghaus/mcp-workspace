"""Generic JSON load/save and file paths for the disk caches.

Shape-agnostic: each cache validates and merges its own data.
"""

import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping, Optional

from mcp_coder_utils.user_app_data import get_user_app_data_dir

from mcp_workspace.utils.repo_identifier import RepoIdentifier

logger = logging.getLogger(__name__)

CACHE_DIR_PARTS = ("mcp_coder", "coordinator_cache")

# Delay before the single os.replace retry in _save_cache_file.
_REPLACE_RETRY_DELAY_SECONDS: float = 0.1


def cache_file_path(repo_identifier: RepoIdentifier, suffix: str) -> Path:
    """Get the cache file path for a repository and cache kind.

    Args:
        repo_identifier: Repository identifier with owner and repo name
        suffix: Cache kind, e.g. ``"issues"``, ``"prs"`` or ``"branches"``

    Returns:
        ``<app-data>/mcp_coder/coordinator_cache/<cache_safe_name>.<suffix>.json``
    """
    app_name, subdir = CACHE_DIR_PARTS
    cache_dir = get_user_app_data_dir(app_name) / subdir
    return cache_dir / f"{repo_identifier.cache_safe_name}.{suffix}.json"


def load_json(path: Path, expected_version: int | None = None) -> dict[str, Any]:
    """Load a JSON object from a cache file. Never raises.

    Args:
        path: Path to the cache file
        expected_version: If given, data whose ``version`` differs (or is
            missing) is treated as empty

    Returns:
        The loaded dict, or ``{}`` for a missing, corrupt, non-object or
        version-mismatched file.
    """
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
        logger.warning(f"Cache load error for {path}: {e}, starting fresh")
        return {}
    if not isinstance(data, dict):
        return {}
    if expected_version is not None and data.get("version") != expected_version:
        logger.debug(
            f"Cache version mismatch for {path}: "
            f"{data.get('version')!r} != {expected_version}, starting fresh"
        )
        return {}
    return data


def _save_cache_file(cache_file_path: Path, cache_data: Mapping[str, Any]) -> bool:
    """Save cache data to file using atomic write.

    Each save writes to its own unique temp file in the target directory, so
    concurrent writers never share a temp path. The final ``os.replace`` is
    retried once after a short delay (Windows can briefly lock the target).
    The temp file is removed on every failure path.

    Args:
        cache_file_path: Path to cache file
        cache_data: CacheData to save

    Returns:
        True if successful, False otherwise
    """
    temp_path: Optional[str] = None
    try:
        # Ensure directory exists
        cache_file_path.parent.mkdir(parents=True, exist_ok=True)

        # Atomic write: write to unique temp file, then rename
        fd, temp_path = tempfile.mkstemp(
            dir=cache_file_path.parent,
            prefix=cache_file_path.name + ".",
            suffix=".tmp",
        )
        with os.fdopen(fd, "w") as f:
            json.dump(cache_data, f, indent=2)

        try:
            os.replace(temp_path, cache_file_path)  # Atomic rename
        except OSError:
            # Single retry; a second failure falls through to the outer handler
            time.sleep(_REPLACE_RETRY_DELAY_SECONDS)
            os.replace(temp_path, cache_file_path)
        return True

    except OSError as e:
        logger.warning(f"Cache save error for {cache_file_path}: {e}")
        return False

    finally:
        if temp_path is not None:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except OSError:
                pass
