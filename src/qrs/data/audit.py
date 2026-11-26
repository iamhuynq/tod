"""P0 archive audit: symbol coverage and point-in-time universe reconstruction.

Downloads only daily (1d) klines inside the development period. Listing metadata
after the development period is discarded so no holdout-period information is stored.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import httpx
import polars as pl

from qrs.data.archive import ChecksumMismatchError, download_verified, list_prefix
from qrs.data.holdout_guard import assert_development_range, assert_not_holdout_path
from qrs.data.klines import read_kline_zip
from qrs.data.paths import ProjectPaths
from qrs.data.universe import (
    base_asset,
    detect_pegged,
    exclusion_reason,
    month_starts,
    monthly_ranking,
)
from qrs.protocol import Protocol

KLINES_PREFIX = "data/spot/monthly/klines/"
_MONTH_RE = re.compile(r"-1d-(\d{4})-(\d{2})\.zip$")


@dataclass
class AuditResult:
    symbols: pl.DataFrame
    ranking: pl.DataFrame
    membership: pl.DataFrame
    months: pl.DataFrame
    failures: list[tuple[str, date, str]] = field(default_factory=list)


def _month_end(m: date) -> date:
    nxt = date(m.year + (m.month == 12), m.month % 12 + 1, 1)
    return nxt - timedelta(days=1)


async def _list_symbol_months(
    client: httpx.AsyncClient, symbol: str, sem: asyncio.Semaphore
) -> list[date]:
    async with sem:
        _, objects = await list_prefix(client, f"{KLINES_PREFIX}{symbol}/1d/")
    months = []
    for o in objects:
        m = _MONTH_RE.search(o.key)
        if m:
            months.append(date(int(m.group(1)), int(m.group(2)), 1))
    return sorted(months)


async def _download_month(
    client: httpx.AsyncClient,
    paths: ProjectPaths,
    symbol: str,
    month: date,
    sem: asyncio.Semaphore,
) -> Path:
    name = f"{symbol}-1d-{month:%Y-%m}.zip"
    dest = paths.dev / "raw" / "klines_1d" / symbol / name
    assert_not_holdout_path(dest, paths)
    async with sem:
        return await download_verified(client, f"{KLINES_PREFIX}{symbol}/1d/{name}", dest)


async def run_audit(
    paths: ProjectPaths,
    protocol: Protocol,
    universe_size: int = 15,
    concurrency: int = 16,
    symbol_limit: int | None = None,
) -> AuditResult:
    dev_start, dev_end = protocol.development.start, protocol.development_end
    rank_months = month_starts(dev_start, dev_end)
    data_months = month_starts(rank_months[0] - timedelta(days=31), rank_months[-1] - timedelta(1))
    for m in data_months:
        if _month_end(m) > dev_end:
            raise AssertionError(f"data month {m} extends past development end")
    sem = asyncio.Semaphore(concurrency)
    limits = httpx.Limits(max_connections=concurrency)
    async with httpx.AsyncClient(timeout=60, limits=limits, follow_redirects=True) as client:
        prefixes, _ = await list_prefix(client, KLINES_PREFIX)
        all_symbols = sorted(p[len(KLINES_PREFIX) :].rstrip("/") for p in prefixes)
        usdt = [s for s in all_symbols if base_asset(s) is not None]
        bases = {b for s in usdt if (b := base_asset(s)) is not None}
        reasons = {s: exclusion_reason(s, bases) for s in usdt}
        candidates = [s for s in usdt if reasons[s] is None][:symbol_limit]

        listed = await asyncio.gather(*(_list_symbol_months(client, s, sem) for s in candidates))
        # Discard listing information after the development period.
        avail = {
            s: [m for m in ms if _month_end(m) <= dev_end]
            for s, ms in zip(candidates, listed, strict=True)
        }
        wanted = set(data_months)
        jobs = [(s, m) for s, ms in avail.items() for m in ms if m in wanted]
        for _, m in jobs:
            assert_development_range(dev_start, max(dev_start, _month_end(m)), protocol)
        results = await asyncio.gather(
            *(_download_month(client, paths, s, m, sem) for s, m in jobs), return_exceptions=True
        )

    failures: list[tuple[str, date, str]] = []
    frames = []
    for (s, m), res in zip(jobs, results, strict=True):
        if isinstance(res, BaseException):
            kind = "checksum" if isinstance(res, ChecksumMismatchError) else type(res).__name__
            failures.append((s, m, kind))
            continue
        frames.append(read_kline_zip(res).with_columns(pl.lit(s).alias("symbol")))

    daily = (
        pl.concat(frames)
        .with_columns(pl.from_epoch("open_time", time_unit="ms").dt.date().alias("day"))
        .unique(subset=["symbol", "day"], keep="first")
        .sort("symbol", "day")
        if frames
        else pl.DataFrame(schema={"symbol": pl.String, "day": pl.Date, "close": pl.Float64,
                                  "quote_volume": pl.Float64})
    )  # fmt: skip
    pegged = detect_pegged(daily) if daily.height else set()
    first_available = {s: ms[0] for s, ms in avail.items() if ms and s not in pegged}
    ranking = monthly_ranking(
        daily.select("symbol", "day", "quote_volume"), first_available, rank_months
    )
    membership = ranking.filter(pl.col("rank") <= universe_size)

    # Keep excluded symbols (rule-based, no listing needed) and candidates with
    # development-period data. Symbols that only exist after it are not recorded.
    kept = [s for s in usdt if reasons[s] is not None or avail.get(s)]
    symbols = pl.DataFrame(
        {
            "symbol": kept,
            "exclusion_reason": ["pegged_price" if s in pegged else reasons[s] for s in kept],
            "first_month": [avail[s][0] if avail.get(s) else None for s in kept],
            "last_month_in_dev": [avail[s][-1] if avail.get(s) else None for s in kept],
        },
        schema_overrides={"first_month": pl.Date, "last_month_in_dev": pl.Date},
    )
    months = _month_confidence(rank_months, membership, failures, universe_size)
    out = paths.dev / "universe"
    out.mkdir(parents=True, exist_ok=True)
    daily.write_parquet(paths.dev / "klines_1d.parquet")
    symbols.write_parquet(out / "symbols.parquet")
    ranking.write_parquet(out / "ranking.parquet")
    membership.write_parquet(out / "membership.parquet")
    months.write_parquet(out / "months.parquet")
    return AuditResult(symbols, ranking, membership, months, failures)


def _month_confidence(
    rank_months: list[date],
    membership: pl.DataFrame,
    failures: list[tuple[str, date, str]],
    expected_size: int,
) -> pl.DataFrame:
    """high: no download failures in the ranking window.
    medium: failures only for symbols that were not members in adjacent months.
    low: a failed symbol was a member in an adjacent month (it may be wrongly missing),
    or the month has fewer members than expected."""

    def members_of(month: date) -> set[str]:
        return set(membership.filter(pl.col("month") == month)["symbol"].to_list())

    rows = []
    for i, m in enumerate(rank_months):
        lo, hi = m - timedelta(days=30), m - timedelta(days=1)
        window_months = {date(lo.year, lo.month, 1), date(hi.year, hi.month, 1)}
        failed = {s for s, fm, _ in failures if fm in window_months}
        members = members_of(m)
        adjacent = set().union(*(members_of(rank_months[j]) for j in (i - 1, i + 1)
                                 if 0 <= j < len(rank_months)))  # fmt: skip
        if (failed & (members | adjacent)) or len(members) < expected_size:
            conf = "low"
        elif failed:
            conf = "medium"
        else:
            conf = "high"
        rows.append(
            {"month": m, "members": len(members), "failed_symbols": len(failed), "confidence": conf}
        )
    schema = {
        "month": pl.Date,
        "members": pl.Int64,
        "failed_symbols": pl.Int64,
        "confidence": pl.String,
    }
    return pl.DataFrame(rows, schema=schema)
