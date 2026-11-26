from datetime import date, timedelta

import polars as pl

from qrs.data.universe import (
    detect_pegged,
    exclusion_reason,
    month_starts,
    monthly_ranking,
)

BASES = {"BTC", "ETH", "JUP", "BTCUP", "ETHDOWN", "USDC"}


def test_exclusions() -> None:
    assert exclusion_reason("BTCUSDT", BASES) is None
    assert exclusion_reason("JUPUSDT", BASES) is None  # ends with UP but is not leveraged
    assert exclusion_reason("BTCUPUSDT", BASES) == "leveraged_token"
    assert exclusion_reason("ETHDOWNUSDT", BASES) == "leveraged_token"
    assert exclusion_reason("USDCUSDT", BASES) == "stable_or_fiat"
    assert exclusion_reason("BTCBUSD", BASES) == "not_usdt_quote"


def test_month_starts() -> None:
    assert month_starts(date(2021, 11, 15), date(2022, 2, 1)) == [
        date(2021, 11, 1),
        date(2021, 12, 1),
        date(2022, 1, 1),
        date(2022, 2, 1),
    ]


def _daily(symbol: str, start: date, days: int, qv: float, close: float = 10.0) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "symbol": [symbol] * days,
            "day": [start + timedelta(days=i) for i in range(days)],
            "quote_volume": [qv] * days,
            "close": [close] * days,
        }
    )


def test_ranking_uses_only_prior_data() -> None:
    m = date(2022, 3, 1)
    # A is larger before March; B becomes huge only from March 1 onward (must be ignored).
    daily = pl.concat(
        [
            _daily("A", date(2022, 1, 1), 59, 100.0),
            _daily("B", date(2022, 1, 1), 59, 10.0),
            _daily("B", m, 10, 1e9),
        ]
    ).select("symbol", "day", "quote_volume")
    first = {"A": date(2021, 1, 1), "B": date(2021, 1, 1)}
    r = monthly_ranking(daily, first, [m])
    assert r.sort("rank")["symbol"].to_list() == ["A", "B"]


def test_ranking_requires_history_and_activity() -> None:
    m = date(2022, 3, 1)
    daily = pl.concat(
        [
            _daily("OLD", date(2022, 1, 1), 59, 1.0),
            _daily("NEW", date(2022, 1, 1), 59, 1e6),  # listed too recently
            _daily("THIN", date(2022, 2, 20), 9, 1e6),  # too few active days
        ]
    ).select("symbol", "day", "quote_volume")
    first = {"OLD": date(2021, 1, 1), "NEW": date(2022, 1, 15), "THIN": date(2021, 1, 1)}
    r = monthly_ranking(daily, first, [m])
    assert r["symbol"].to_list() == ["OLD"]


def test_detect_pegged() -> None:
    daily = pl.concat(
        [
            _daily("PEG", date(2022, 1, 1), 30, 1.0, close=1.001),
            _daily("X", date(2022, 1, 1), 30, 1.0),
        ]
    )
    assert detect_pegged(daily) == {"PEG"}
