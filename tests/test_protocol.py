from pathlib import Path

import pytest

from qrs.protocol import ProtocolError, load_protocol

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_repo_protocol_loads() -> None:
    p = load_protocol(REPO_ROOT / "protocol" / "protocol.yaml")
    assert p.status == "draft"
    assert p.development.end is not None
    assert p.development.end < p.holdout_a.start
    assert p.universe.min_history_days == 180
    assert p.universe.engineering_symbols == (
        "BTCUSDT",
        "ETHUSDT",
        "BNBUSDT",
        "SOLUSDT",
        "XRPUSDT",
    )


UNIVERSE = """
universe:
  size_p1_p4: 15
  min_history_days: 180
  ranking_window_days: 30
  min_active_days: 20
  engineering_symbols: [BTCUSDT]
"""


def _write(tmp_path: Path, body: str) -> Path:
    f = tmp_path / "protocol.yaml"
    f.write_text(body, encoding="utf-8")
    return f


def test_overlapping_periods_rejected(tmp_path: Path) -> None:
    f = _write(
        tmp_path,
        """
protocol_version: "x"
status: draft
periods:
  development: {start: "2022-01-01", end: "2025-12-15"}
  holdout_a: {start: "2025-12-01", end: "2026-05-31"}
  holdout_b: {start: "2026-06-01", end: null}
"""
        + UNIVERSE,
    )
    with pytest.raises(ProtocolError, match="development must end before holdout_a"):
        load_protocol(f)


def test_frozen_requires_freeze_timestamp(tmp_path: Path) -> None:
    f = _write(
        tmp_path,
        """
protocol_version: "x"
status: frozen
freeze_timestamp: null
periods:
  development: {start: "2022-01-01", end: "2025-11-30"}
  holdout_a: {start: "2025-12-01", end: "2026-05-31"}
  holdout_b: {start: "2026-06-01", end: "2026-11-30"}
"""
        + UNIVERSE,
    )
    with pytest.raises(ProtocolError, match="frozen protocol needs freeze_timestamp"):
        load_protocol(f)


VALID_PERIODS = """
protocol_version: "x"
status: draft
periods:
  development: {start: "2022-01-01", end: "2025-11-30"}
  holdout_a: {start: "2025-12-01", end: "2026-05-31"}
  holdout_b: {start: "2026-06-01", end: null}
"""


def test_missing_universe_rejected(tmp_path: Path) -> None:
    with pytest.raises(ProtocolError, match="universe section is missing"):
        load_protocol(_write(tmp_path, VALID_PERIODS))


def test_active_days_outside_window_rejected(tmp_path: Path) -> None:
    body = VALID_PERIODS + UNIVERSE.replace("min_active_days: 20", "min_active_days: 31")
    with pytest.raises(ProtocolError, match="min_active_days"):
        load_protocol(_write(tmp_path, body))
