import click.testing

from hive.cli.app import cli


class TestRootHelp:
    def test_help_output(self):
        runner = click.testing.CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Hive" in result.output

    def test_no_args_shows_help(self):
        runner = click.testing.CliRunner()
        result = runner.invoke(cli, [])
        assert "Hive" in result.output
