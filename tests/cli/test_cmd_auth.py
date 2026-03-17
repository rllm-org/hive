from hive.cli.hive import hive


class TestAuthRegister:
    def test_register(self, cli_env):
        result = cli_env.invoke(hive, ["auth", "register"])
        assert result.exit_code == 0
        assert "Registered as:" in result.output


class TestAuthWhoami:
    def test_not_registered(self, cli_env):
        result = cli_env.invoke(hive, ["auth", "whoami"])
        assert result.exit_code != 0
