from typer.testing import CliRunner

from qrs.cli.main import app

runner = CliRunner()


def test_info() -> None:
    result = runner.invoke(app, ["info"])
    assert result.exit_code == 0, result.output
    assert "protocol 1.2 (frozen)" in result.output


def test_check_path_rejects_holdout() -> None:
    result = runner.invoke(app, ["check-path", "data/holdout/BTCUSDT/x.parquet"])
    assert result.exit_code == 1


def test_check_path_allows_dev() -> None:
    result = runner.invoke(app, ["check-path", "data/dev/BTCUSDT/x.parquet"])
    assert result.exit_code == 0
