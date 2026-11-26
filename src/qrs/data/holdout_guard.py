"""Holdout guard: blocks research code from reading holdout data.

P0 scope: path and date checks used by every data loader.
P3 adds the approved access path (validation.final_holdout) with approval tokens
and the holdout_access_log table. Until then, no code path may read holdout data.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from qrs.data.paths import ProjectPaths
from qrs.protocol import Protocol


class HoldoutAccessError(PermissionError):
    """Raised when non-validation code tries to touch holdout data."""


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def assert_not_holdout_path(path: Path, paths: ProjectPaths) -> None:
    """Reject any path inside the holdout data root (symlinks are resolved)."""
    if _is_within(path, paths.holdout):
        raise HoldoutAccessError(f"access to holdout data is not allowed: {path}")


def assert_development_range(start: date, end: date, protocol: Protocol) -> None:
    """Reject a requested date range that extends past the development period."""
    if start > end:
        raise ValueError(f"start {start} is after end {end}")
    if start < protocol.development.start:
        raise ValueError(f"start {start} is before development start {protocol.development.start}")
    if end > protocol.development_end:
        raise HoldoutAccessError(
            f"requested end {end} is after development end {protocol.development_end}"
        )
