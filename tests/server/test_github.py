import os
import pytest
from hive.server.github import GitHubApp, get_github_app, set_github_app


class TestGitHubAppHelpers:
    def test_set_and_get(self):
        from tests.mocks import MockGitHubApp
        mock = MockGitHubApp()
        set_github_app(mock)
        assert get_github_app() is mock

    def test_mock_create_fork(self):
        from tests.mocks import MockGitHubApp
        mock = MockGitHubApp()
        result = mock.create_fork("org/repo", "repo--agent")
        assert "fork_url" in result
        assert "ssh_url" in result

    def test_mock_generate_keypair(self):
        from tests.mocks import MockGitHubApp
        mock = MockGitHubApp()
        priv, pub = mock.generate_ssh_keypair()
        assert priv
        assert pub


class TestGitHubAppReal:
    """Tests against the real GitHubApp class (no mock) to catch import errors."""

    def test_jwt_importable(self):
        """Catch missing PyJWT dependency."""
        import jwt  # noqa: F401

    def test_get_token_requires_credentials(self):
        """get_token raises if no credentials configured."""
        app = GitHubApp("", "", "test-org", "")
        env = os.environ.pop("GITHUB_APP_INSTALLATION_TOKEN", None)
        try:
            with pytest.raises(RuntimeError, match="credentials not configured"):
                app.get_token()
        finally:
            if env is not None:
                os.environ["GITHUB_APP_INSTALLATION_TOKEN"] = env

    def test_get_token_uses_env_var(self, monkeypatch):
        """get_token reads GITHUB_APP_INSTALLATION_TOKEN env var."""
        monkeypatch.setenv("GITHUB_APP_INSTALLATION_TOKEN", "test-token-123")
        app = GitHubApp("", "", "test-org", "")
        assert app.get_token() == "test-token-123"

    def test_generate_ssh_keypair(self):
        """Real ssh-keygen works."""
        app = GitHubApp("", "", "test-org", "")
        priv, pub = app.generate_ssh_keypair()
        assert "PRIVATE KEY" in priv
        assert pub.startswith("ssh-ed25519")
