"""Load and validate the research protocol (protocol/protocol.yaml)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml


class ProtocolError(ValueError):
    """Raised when the protocol file is missing fields or is inconsistent."""


@dataclass(frozen=True)
class Period:
    start: date
    end: date | None

    def contains(self, day: date) -> bool:
        return day >= self.start and (self.end is None or day <= self.end)


@dataclass(frozen=True)
class UniverseConfig:
    size: int
    min_history_days: int
    ranking_window_days: int
    min_active_days: int
    engineering_symbols: tuple[str, ...]


@dataclass(frozen=True)
class Protocol:
    version: str
    status: str
    development: Period
    holdout_a: Period
    holdout_b: Period
    universe: UniverseConfig
    raw: dict[str, Any]

    @property
    def is_frozen(self) -> bool:
        return self.status == "frozen"

    @property
    def development_end(self) -> date:
        assert self.development.end is not None  # enforced in _validate
        return self.development.end


def _parse_date(value: Any, field: str) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise ProtocolError(f"{field}: expected ISO date string, got {value!r}")


def _period(raw: dict[str, Any], name: str) -> Period:
    try:
        block = raw["periods"][name]
    except (KeyError, TypeError) as exc:
        raise ProtocolError(f"periods.{name} is missing") from exc
    start = _parse_date(block.get("start"), f"periods.{name}.start")
    if start is None:
        raise ProtocolError(f"periods.{name}.start is required")
    return Period(start=start, end=_parse_date(block.get("end"), f"periods.{name}.end"))


def _universe(raw: dict[str, Any]) -> UniverseConfig:
    u = raw.get("universe")
    if not isinstance(u, dict):
        raise ProtocolError("universe section is missing")
    try:
        cfg = UniverseConfig(
            size=int(u["size_p1_p4"]),
            min_history_days=int(u["min_history_days"]),
            ranking_window_days=int(u["ranking_window_days"]),
            min_active_days=int(u["min_active_days"]),
            engineering_symbols=tuple(str(s) for s in u["engineering_symbols"]),
        )
    except KeyError as exc:
        raise ProtocolError(f"universe.{exc.args[0]} is required") from exc
    if cfg.size < 1 or cfg.min_history_days < 0 or cfg.ranking_window_days < 1:
        raise ProtocolError("universe values must be positive")
    if not 0 < cfg.min_active_days <= cfg.ranking_window_days:
        raise ProtocolError("universe.min_active_days must be within the ranking window")
    if not cfg.engineering_symbols:
        raise ProtocolError("universe.engineering_symbols must not be empty")
    return cfg


def _validate(p: Protocol) -> None:
    if p.status not in {"draft", "frozen"}:
        raise ProtocolError(f"status must be 'draft' or 'frozen', got {p.status!r}")
    if p.development.end is None:
        raise ProtocolError("periods.development.end is required")
    if p.holdout_a.end is None:
        raise ProtocolError("periods.holdout_a.end is required")
    if not p.development.end < p.holdout_a.start:
        raise ProtocolError("development must end before holdout_a starts")
    if not p.holdout_a.end < p.holdout_b.start:
        raise ProtocolError("holdout_a must end before holdout_b starts")
    if p.is_frozen and (p.raw.get("freeze_timestamp") is None or p.holdout_b.end is None):
        raise ProtocolError("a frozen protocol needs freeze_timestamp and periods.holdout_b.end")


def load_protocol(path: Path) -> Protocol:
    if not path.is_file():
        raise ProtocolError(f"protocol file not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ProtocolError("protocol file must be a mapping")
    protocol = Protocol(
        version=str(raw.get("protocol_version", "")),
        status=str(raw.get("status", "")),
        development=_period(raw, "development"),
        holdout_a=_period(raw, "holdout_a"),
        holdout_b=_period(raw, "holdout_b"),
        universe=_universe(raw),
        raw=raw,
    )
    _validate(protocol)
    return protocol
