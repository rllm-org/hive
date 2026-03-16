import os
import subprocess
import tempfile
import time

import httpx

_GITHUB_API = "https://api.github.com"


class GitHubApp:
    """Abstraction over GitHub App API for fork management.

    All GitHub API calls go through this class so it can be mocked in tests.
    """

    def __init__(self, app_id: str, private_key: str, org: str,
                 installation_id: str = ""):
        self.app_id = app_id
        self.private_key = private_key
        self.org = org
        self.installation_id = installation_id
        self._cached_token = ""
        self._token_expires = 0

    def _get_token(self) -> str:
        # Use env var if set (for testing / manual override)
        env_token = os.environ.get("GITHUB_APP_INSTALLATION_TOKEN")
        if env_token:
            return env_token
        # Auto-generate from App credentials
        if not self.app_id or not self.private_key or not self.installation_id:
            raise RuntimeError("GitHub App credentials not configured")
        now = int(time.time())
        if self._cached_token and now < self._token_expires - 60:
            return self._cached_token
        import jwt
        encoded = jwt.encode({"iat": now - 60, "exp": now + 600, "iss": self.app_id},
                             self.private_key, algorithm="RS256")
        resp = httpx.post(
            f"{_GITHUB_API}/app/installations/{self.installation_id}/access_tokens",
            headers={"Authorization": f"Bearer {encoded}",
                     "Accept": "application/vnd.github+json"}, timeout=15)
        resp.raise_for_status()
        self._cached_token = resp.json()["token"]
        self._token_expires = now + 3500  # ~58 min cache
        return self._cached_token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def create_fork(self, upstream_repo: str, fork_name: str) -> dict:
        """Create a fork of upstream_repo under self.org with the given name."""
        # Check if fork already exists
        existing = httpx.get(
            f"{_GITHUB_API}/repos/{self.org}/{fork_name}",
            headers=self._headers(), timeout=15,
        )
        if existing.status_code == 200:
            data = existing.json()
            return {"fork_url": data["html_url"], "ssh_url": data["ssh_url"]}

        resp = httpx.post(
            f"{_GITHUB_API}/repos/{upstream_repo}/forks",
            headers=self._headers(),
            json={"organization": self.org, "name": fork_name},
            timeout=30,
        )
        resp.raise_for_status()

        # Poll until fork is ready (fork creation is async)
        for _ in range(30):
            time.sleep(2)
            check = httpx.get(
                f"{_GITHUB_API}/repos/{self.org}/{fork_name}",
                headers=self._headers(), timeout=15,
            )
            if check.status_code == 200:
                data = check.json()
                return {"fork_url": data["html_url"], "ssh_url": data["ssh_url"]}

        raise RuntimeError(f"Fork {self.org}/{fork_name} did not become ready in time")

    def add_deploy_key(self, repo_full_name: str, title: str, public_key: str) -> int:
        """Add a deploy key with write access to a repo. Returns key ID."""
        resp = httpx.post(
            f"{_GITHUB_API}/repos/{repo_full_name}/keys",
            headers=self._headers(),
            json={"title": title, "key": public_key, "read_only": False},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()["id"]

    def remove_deploy_key(self, repo_full_name: str, key_id: int) -> None:
        """Remove a deploy key from a repo."""
        resp = httpx.delete(
            f"{_GITHUB_API}/repos/{repo_full_name}/keys/{key_id}",
            headers=self._headers(),
            timeout=15,
        )
        resp.raise_for_status()

    def set_branch_protection(self, repo_full_name: str, branch: str) -> None:
        """Set branch protection: no force-push, no deletion."""
        resp = httpx.put(
            f"{_GITHUB_API}/repos/{repo_full_name}/branches/{branch}/protection",
            headers=self._headers(),
            json={
                "required_status_checks": None,
                "enforce_admins": False,
                "required_pull_request_reviews": None,
                "restrictions": None,
                "allow_force_pushes": False,
                "allow_deletions": False,
            },
            timeout=15,
        )
        resp.raise_for_status()

    def generate_ssh_keypair(self) -> tuple[str, str]:
        """Generate an ed25519 SSH keypair. Returns (private_key, public_key)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            key_path = os.path.join(tmpdir, "id_ed25519")
            subprocess.run(
                ["ssh-keygen", "-t", "ed25519", "-N", "", "-f", key_path],
                check=True, capture_output=True,
            )
            private_key = open(key_path).read()
            public_key = open(key_path + ".pub").read().strip()
        return private_key, public_key


_github_app: "GitHubApp | None" = None


def get_github_app() -> GitHubApp:
    """Return singleton GitHubApp instance, created from env vars."""
    global _github_app
    if _github_app is None:
        app_id = os.environ.get("GITHUB_APP_ID", "")
        pk = os.environ.get("GITHUB_APP_PRIVATE_KEY", "")
        pk_file = os.environ.get("GITHUB_APP_PRIVATE_KEY_FILE", "")
        if not pk and pk_file and os.path.isfile(pk_file):
            pk = open(pk_file).read()
        org = os.environ.get("GITHUB_ORG", "hive-agents")
        inst_id = os.environ.get("GITHUB_APP_INSTALLATION_ID", "")
        _github_app = GitHubApp(app_id, pk, org, inst_id)
    return _github_app


def set_github_app(app: GitHubApp) -> None:
    """Override the GitHubApp instance (for testing)."""
    global _github_app
    _github_app = app
