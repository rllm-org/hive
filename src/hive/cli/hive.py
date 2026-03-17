# Backward-compat shim — tests and entry point import from here
from hive.cli.app import app, cli  # noqa: F401
from hive.cli.helpers import _parse_since  # noqa: F401

hive = cli  # Click Group that setuptools and CliRunner can invoke

if __name__ == "__main__":
    hive()
