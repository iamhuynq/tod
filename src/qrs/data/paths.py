"""Filesystem layout for market data and protocol files."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT_ENV_VAR = "QRS_ROOT"


def _find_project_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "pyproject.toml").is_file() and (candidate / "protocol").is_dir():
            return candidate
    raise FileNotFoundError(f"Could not locate project root above {start}")


@dataclass(frozen=True)
class ProjectPaths:
    root: Path

    @property
    def protocol_file(self) -> Path:
        return self.root / "protocol" / "protocol.yaml"

    @property
    def data_root(self) -> Path:
        return self.root / "data"

    @property
    def dev(self) -> Path:
        return self.data_root / "dev"

    @property
    def holdout(self) -> Path:
        return self.data_root / "holdout"

    @property
    def live(self) -> Path:
        return self.data_root / "live"

    @property
    def metadata_db(self) -> Path:
        return self.data_root / "metadata.sqlite"


def get_paths(root: Path | None = None) -> ProjectPaths:
    """Resolve project paths from an explicit root, $QRS_ROOT, or the source location."""
    if root is not None:
        return ProjectPaths(root.resolve())
    env_root = os.environ.get(ROOT_ENV_VAR)
    if env_root:
        return ProjectPaths(Path(env_root).resolve())
    return ProjectPaths(_find_project_root(Path(__file__).resolve().parent))
