from datetime import date
from pathlib import Path

import pytest

from qrs.data.holdout_guard import (
    HoldoutAccessError,
    assert_development_range,
    assert_not_holdout_path,
)
from qrs.data.paths import ProjectPaths
from qrs.protocol import load_protocol

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def paths(tmp_path: Path) -> ProjectPaths:
    p = ProjectPaths(tmp_path)
    p.dev.mkdir(parents=True)
    p.holdout.mkdir(parents=True)
    return p


def test_dev_path_allowed(paths: ProjectPaths) -> None:
    assert_not_holdout_path(paths.dev / "BTCUSDT" / "2024-01.parquet", paths)


def test_holdout_path_rejected(paths: ProjectPaths) -> None:
    with pytest.raises(HoldoutAccessError):
        assert_not_holdout_path(paths.holdout / "BTCUSDT" / "2026-01.parquet", paths)


def test_holdout_path_via_dotdot_rejected(paths: ProjectPaths) -> None:
    sneaky = paths.dev / ".." / "holdout" / "x.parquet"
    with pytest.raises(HoldoutAccessError):
        assert_not_holdout_path(sneaky, paths)


def test_holdout_path_via_symlink_rejected(paths: ProjectPaths) -> None:
    link = paths.dev / "link"
    link.symlink_to(paths.holdout, target_is_directory=True)
    with pytest.raises(HoldoutAccessError):
        assert_not_holdout_path(link / "x.parquet", paths)


def test_development_range() -> None:
    protocol = load_protocol(REPO_ROOT / "protocol" / "protocol.yaml")
    assert_development_range(date(2022, 1, 1), date(2025, 11, 30), protocol)
    with pytest.raises(HoldoutAccessError):
        assert_development_range(date(2025, 11, 1), date(2025, 12, 1), protocol)
    with pytest.raises(ValueError):
        assert_development_range(date(2021, 12, 31), date(2022, 2, 1), protocol)
