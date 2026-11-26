"""Single CLI entry point: `qrs <command>`."""

from __future__ import annotations

from pathlib import Path

import typer

from qrs import __version__
from qrs.data.holdout_guard import HoldoutAccessError, assert_not_holdout_path
from qrs.data.paths import get_paths
from qrs.protocol import load_protocol

app = typer.Typer(help="Autonomous Quant Research System", no_args_is_help=True)


@app.command()
def info() -> None:
    """Show version, protocol status and data locations."""
    paths = get_paths()
    protocol = load_protocol(paths.protocol_file)
    typer.echo(f"qrs {__version__}")
    typer.echo(f"protocol {protocol.version} ({protocol.status})")
    typer.echo(f"development {protocol.development.start} .. {protocol.development.end}")
    typer.echo(f"data root {paths.data_root}")


@app.command("check-path")
def check_path(path: Path) -> None:
    """Exit non-zero if PATH is inside the holdout data root."""
    try:
        assert_not_holdout_path(path, get_paths())
    except HoldoutAccessError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo("ok")


@app.command("audit-archive")
def audit_archive(
    concurrency: int = typer.Option(16, help="Parallel HTTP requests"),
    symbol_limit: int | None = typer.Option(None, help="Limit candidates (smoke runs)"),
    report: Path = typer.Option(
        Path("docs/phase-reports/P0-archive-audit.md"), help="Markdown report path"
    ),
) -> None:
    """P0: audit archive coverage and rebuild the point-in-time universe.

    Universe parameters come from protocol/protocol.yaml (universe section)."""
    import asyncio

    from qrs.data.audit import run_audit
    from qrs.reporting.audit_report import render_audit_report

    paths = get_paths()
    protocol = load_protocol(paths.protocol_file)
    result = asyncio.run(run_audit(paths, protocol, concurrency, symbol_limit))
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(render_audit_report(result, protocol.version), encoding="utf-8")
    typer.echo(f"symbols={result.symbols.height} failures={len(result.failures)}")
    typer.echo(f"report: {report}")


if __name__ == "__main__":
    app()
