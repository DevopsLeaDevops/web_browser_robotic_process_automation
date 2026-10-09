from click.testing import CliRunner

import rpa_cli
import rpa_core
from rpa_cli.main import cli


def test_version_shows_cli_and_core_versions() -> None:
    result = CliRunner().invoke(cli, ["--version"])

    assert result.exit_code == 0
    assert rpa_cli.__version__ in result.output
    assert f"rpa-core {rpa_core.__version__}" in result.output


def test_help_is_available() -> None:
    result = CliRunner().invoke(cli, ["-h"])

    assert result.exit_code == 0
    assert "瀏覽器自動化" in result.output
