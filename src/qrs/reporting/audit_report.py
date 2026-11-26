"""Markdown report for the P0 archive audit."""

from __future__ import annotations

from datetime import UTC, datetime

import polars as pl

from qrs.data.audit import AuditResult


def render_audit_report(result: AuditResult, protocol_version: str) -> str:
    s = result.symbols
    reasons = (
        s.group_by(pl.col("exclusion_reason").fill_null("included"))
        .len()
        .sort("len", descending=True)
    )
    with_data = s.filter(pl.col("first_month").is_not_null() & pl.col("exclusion_reason").is_null())
    last_dev_month = with_data["last_month_in_dev"].max()
    delisted = with_data.filter(pl.col("last_month_in_dev") < last_dev_month)
    conf = result.months.group_by("confidence").len().sort("confidence")
    churn = (
        result.membership.sort("month")
        .group_by("month", maintain_order=True)
        .agg(pl.col("symbol").sort().str.join(", ").alias("members"))
    )
    ever = result.membership["symbol"].unique().sort().to_list()

    lines = [
        "# P0 Archive Audit",
        "",
        f"Generated: {datetime.now(UTC):%Y-%m-%d %H:%M} UTC  ",
        f"Protocol: {protocol_version}  ",
        "Source: data.binance.vision spot monthly 1d klines (SHA-256 verified)  ",
        "Scope: development period only; listing data after it was discarded.",
        "",
        "## Symbols",
        "",
        f"- USDT-quoted symbols in archive: {s.height}",
        f"- Included candidates with development-period data: {with_data.height}",
        f"- Candidates whose data ends before the last development month "
        f"(delisted or halted): {delisted.height}",
        "",
        "| Exclusion reason | Count |",
        "|---|---|",
        *[f"| {r} | {n} |" for r, n in reasons.iter_rows()],
        "",
        "## Download integrity",
        "",
        f"- Failed monthly files: {len(result.failures)}",
        *[f"  - {sym} {m:%Y-%m}: {kind}" for sym, m, kind in result.failures[:50]],
        "",
        "## Reconstruction confidence by month",
        "",
        "| Confidence | Months |",
        "|---|---|",
        *[f"| {c} | {n} |" for c, n in conf.iter_rows()],
        "",
        f"Symbols that were ever in the top universe: {len(ever)}",
        "",
        ", ".join(ever),
        "",
        "## Monthly membership",
        "",
        "| Month | Members |",
        "|---|---|",
        *[f"| {m:%Y-%m} | {members} |" for m, members in churn.iter_rows()],
        "",
    ]
    return "\n".join(lines)
