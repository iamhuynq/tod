"""Point-in-time universe: symbol filters and monthly liquidity ranking.

Ranking for month M uses only daily bars strictly before the first day of M.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

import polars as pl

QUOTE = "USDT"
# Fiat, stablecoins and pegged assets. Data-driven peg detection supplements this list.
EXCLUDED_BASES = frozenset(
    {
        "USDC", "BUSD", "TUSD", "USDP", "PAX", "DAI", "FDUSD", "USDE", "USDS", "PYUSD",
        "UST", "USTC", "SUSD", "USDSB", "AEUR", "EUR", "EURI", "GBP", "AUD", "BRL",
        "TRY", "RUB", "UAH", "NGN", "ZAR", "BIDR", "IDRT", "BKRW", "PAXG", "XUSD",
    }
)  # fmt: skip
_LEVERAGED_SUFFIX = re.compile(r"^(?P<under>[A-Z0-9]+?)(UP|DOWN|BULL|BEAR)$")


def base_asset(symbol: str) -> str | None:
    return symbol[: -len(QUOTE)] if symbol.endswith(QUOTE) and len(symbol) > len(QUOTE) else None


def exclusion_reason(symbol: str, all_bases: set[str]) -> str | None:
    """Return why a symbol is excluded from the research universe, or None."""
    base = base_asset(symbol)
    if base is None:
        return "not_usdt_quote"
    if base in EXCLUDED_BASES:
        return "stable_or_fiat"
    m = _LEVERAGED_SUFFIX.match(base)
    if m and m.group("under") in all_bases:
        return "leveraged_token"
    return None


def detect_pegged(daily: pl.DataFrame, band: float = 0.03, share: float = 0.9) -> set[str]:
    """Symbols whose close stays within 1 +/- band on at least `share` of days."""
    stats = daily.group_by("symbol").agg(
        ((pl.col("close") - 1.0).abs() <= band).mean().alias("pegged_share")
    )
    return set(stats.filter(pl.col("pegged_share") >= share)["symbol"].to_list())


def month_starts(first: date, last: date) -> list[date]:
    out, d = [], date(first.year, first.month, 1)
    while d <= last:
        out.append(d)
        d = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return out


def monthly_ranking(
    daily: pl.DataFrame,
    first_available: dict[str, date],
    months: list[date],
    window_days: int = 30,
    min_history_days: int = 60,
    min_active_days: int = 20,
) -> pl.DataFrame:
    """Rank eligible symbols by trailing quote volume at each month start.

    daily: columns symbol, day (pl.Date), quote_volume.
    first_available: first date each symbol has archive data (from the listing).
    Returns month, symbol, trailing_quote_volume, active_days, rank.
    """
    frames = []
    for m in months:
        lo, hi = m - timedelta(days=window_days), m - timedelta(days=1)
        eligible = [
            s for s, d in first_available.items() if d <= m - timedelta(days=min_history_days)
        ]
        window = (
            daily.filter(
                pl.col("symbol").is_in(eligible),
                pl.col("day") >= lo,
                pl.col("day") <= hi,
            )
            .group_by("symbol")
            .agg(
                pl.col("quote_volume").sum().alias("trailing_quote_volume"),
                (pl.col("quote_volume") > 0).sum().cast(pl.Int64).alias("active_days"),
            )
            .filter(pl.col("active_days") >= min_active_days)
            .sort("trailing_quote_volume", descending=True)
            .with_columns(
                pl.lit(m).alias("month"),
                pl.int_range(1, pl.len() + 1, dtype=pl.Int64).alias("rank"),
            )
        )
        frames.append(window)
    if not frames:
        return pl.DataFrame(
            schema={
                "symbol": pl.String,
                "trailing_quote_volume": pl.Float64,
                "active_days": pl.Int64,
                "month": pl.Date,
                "rank": pl.Int64,
            }
        )
    return pl.concat(frames).select(
        "month", "symbol", "trailing_quote_volume", "active_days", "rank"
    )
