"""Parse Binance spot kline archive files into normalized Polars frames.

Timestamps are normalized to UTC integer milliseconds. Binance switched spot
archive timestamps from milliseconds to microseconds starting with 2025-01 files.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import polars as pl

KLINE_COLUMNS = [
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_volume",
    "trade_count",
    "taker_buy_base_volume",
    "taker_buy_quote_volume",
    "ignore",
]

_INT_COLS = {"open_time", "close_time", "trade_count"}
# Any epoch value above this is microseconds (ms epochs stay below 1e14 until year 5138).
_MICROSECOND_THRESHOLD = 10**14


def normalize_epoch_ms(col: str) -> pl.Expr:
    c = pl.col(col)
    return pl.when(c >= _MICROSECOND_THRESHOLD).then(c // 1000).otherwise(c).alias(col)


def parse_kline_csv(data: bytes) -> pl.DataFrame:
    text = data.decode("utf-8")
    first = text.split(",", 1)[0].strip()
    has_header = not first.isdigit()
    df = pl.read_csv(
        io.StringIO(text),
        has_header=has_header,
        new_columns=KLINE_COLUMNS,
        schema_overrides={c: (pl.Int64 if c in _INT_COLS else pl.Float64) for c in KLINE_COLUMNS},
    )
    return (
        df.drop("ignore")
        .with_columns(normalize_epoch_ms("open_time"), normalize_epoch_ms("close_time"))
        .sort("open_time")
    )


def read_kline_zip(path: Path) -> pl.DataFrame:
    with zipfile.ZipFile(path) as zf:
        names = [n for n in zf.namelist() if n.endswith(".csv")]
        if len(names) != 1:
            raise ValueError(f"{path}: expected one CSV, found {names}")
        return parse_kline_csv(zf.read(names[0]))
