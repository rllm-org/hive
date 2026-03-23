import os
import subprocess
import tempfile
import time
from pathlib import Path

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

    def get_token(self) -> str:
        """Return a valid GitHub App installation token (cached, auto-refreshed)."""
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

    def headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.get_token()}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def clone_url(self, repo_name: str) -> str:
        """Return an HTTPS clone URL with a fresh installation token."""
        return f"https://x-access-token:{self.get_token()}@github.com/{self.org}/{repo_name}.git"

    def add_deploy_key(self, repo_full_name: str, title: str, public_key: str) -> int:
        """Add a deploy key with write access to a repo. Returns key ID."""
        resp = httpx.post(
            f"{_GITHUB_API}/repos/{repo_full_name}/keys",
            headers=self.headers(),
            json={"title": title, "key": public_key, "read_only": False},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()["id"]

    def remove_deploy_key(self, repo_full_name: str, key_id: int) -> None:
        """Remove a deploy key from a repo."""
        resp = httpx.delete(
            f"{_GITHUB_API}/repos/{repo_full_name}/keys/{key_id}",
            headers=self.headers(),
            timeout=15,
        )
        resp.raise_for_status()

    def set_branch_protection(self, repo_full_name: str, branch: str, lock: bool = False) -> None:
        """Set branch protection. If lock=True, branch is fully read-only."""
        body = {
            "required_status_checks": None,
            "enforce_admins": lock,
            "required_pull_request_reviews": {"required_approving_review_count": 1} if lock else None,
            "restrictions": None,
            "allow_force_pushes": False,
            "allow_deletions": False,
            "lock_branch": lock,
        }
        resp = httpx.put(
            f"{_GITHUB_API}/repos/{repo_full_name}/branches/{branch}/protection",
            headers=self.headers(), json=body, timeout=15,
        )
        resp.raise_for_status()

    def copy_repo(self, source_url: str, repo_name: str) -> dict:
        """Create a standalone repo by bare-cloning source. Returns {"html_url", "ssh_url"}."""
        existing = httpx.get(
            f"{_GITHUB_API}/repos/{self.org}/{repo_name}",
            headers=self.headers(), timeout=15,
        )
        if existing.status_code == 200:
            data = existing.json()
            # If repo exists and has content, return it
            if data.get("size", 0) > 0:
                return {"html_url": data["html_url"], "ssh_url": data["ssh_url"]}
            # Repo exists but is empty — need to push content
        else:
            resp = httpx.post(
                f"{_GITHUB_API}/orgs/{self.org}/repos",
                headers=self.headers(),
                json={"name": repo_name},
                timeout=30,
            )
            resp.raise_for_status()
        # Bare clone source and mirror push to preserve all SHAs
        token = self.get_token()
        push_url = f"https://x-access-token:{token}@github.com/{self.org}/{repo_name}.git"
        with tempfile.TemporaryDirectory() as tmpdir:
            bare = os.path.join(tmpdir, "repo.git")
            subprocess.run(["git", "clone", "--bare", source_url, bare],
                           check=True, capture_output=True, timeout=120)
            subprocess.run(["git", "remote", "set-url", "origin", push_url],
                           cwd=bare, check=True, capture_output=True)
            subprocess.run(["git", "push", "--mirror", push_url],
                           cwd=bare, check=True, capture_output=True, timeout=120)
        info = httpx.get(f"{_GITHUB_API}/repos/{self.org}/{repo_name}",
                         headers=self.headers(), timeout=15).json()
        return {"html_url": info["html_url"], "ssh_url": info["ssh_url"]}

    def create_task_repo(self, task_id: str, archive_bytes: bytes, description: str = "") -> str:
        """Create task--{task_id} repo under org from uploaded archive (tar.gz or zip). Returns repo URL."""
        repo_name = f"task--{task_id}"
        # Create repo (or get existing)
        existing = httpx.get(
            f"{_GITHUB_API}/repos/{self.org}/{repo_name}",
            headers=self.headers(), timeout=15,
        )
        if existing.status_code != 200:
            resp = httpx.post(
                f"{_GITHUB_API}/orgs/{self.org}/repos",
                headers=self.headers(),
                json={"name": repo_name, "description": description, "visibility": "public"},
                timeout=30,
            )
            resp.raise_for_status()

        token = self.get_token()
        push_url = f"https://x-access-token:{token}@github.com/{self.org}/{repo_name}.git"
        with tempfile.TemporaryDirectory() as tmpdir:
            import io, zipfile, tarfile
            buf = io.BytesIO(archive_bytes)
            if zipfile.is_zipfile(buf):
                buf.seek(0)
                with zipfile.ZipFile(buf) as zf:
                    members = [m for m in zf.namelist() if not os.path.basename(m).startswith("._") and not m.startswith("__MACOSX")]
                    zf.extractall(tmpdir, members=members)
            else:
                buf.seek(0)
                tar = tarfile.open(fileobj=buf, mode="r:gz")
                members = [m for m in tar.getmembers() if not os.path.basename(m.name).startswith("._")]
                tar.extractall(tmpdir, members=members, filter="data")
                tar.close()
            subprocess.run(["git", "init"], cwd=tmpdir, check=True, capture_output=True)
            subprocess.run(["git", "add", "."], cwd=tmpdir, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "initial task upload"],
                           cwd=tmpdir, check=True, capture_output=True,
                           env={**os.environ, "GIT_AUTHOR_NAME": "hive", "GIT_AUTHOR_EMAIL": "hive@bot",
                                "GIT_COMMITTER_NAME": "hive", "GIT_COMMITTER_EMAIL": "hive@bot"})
            subprocess.run(["git", "remote", "add", "origin", push_url],
                           cwd=tmpdir, check=True, capture_output=True)
            subprocess.run(["git", "push", "-u", "origin", "HEAD"],
                           cwd=tmpdir, check=True, capture_output=True, timeout=120)
        # Protect default branch so agents can only push to their forks
        try:
            self.set_branch_protection(f"{self.org}/{repo_name}", "main", lock=True)
        except Exception:
            pass  # best-effort; free orgs may not support branch protection
        return f"https://github.com/{self.org}/{repo_name}"

    def generate_ssh_keypair(self) -> tuple[str, str]:
        """Generate an ed25519 SSH keypair. Returns (private_key, public_key)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            key_path = os.path.join(tmpdir, "id_ed25519")
            subprocess.run(
                ["ssh-keygen", "-t", "ed25519", "-N", "", "-f", key_path],
                check=True, capture_output=True,
            )
            private_key = Path(key_path).read_text()
            public_key = Path(key_path + ".pub").read_text().strip()
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
            pk = Path(pk_file).read_text()
        org = os.environ.get("GITHUB_ORG", "hive-agents")
        inst_id = os.environ.get("GITHUB_APP_INSTALLATION_ID", "")
        _github_app = GitHubApp(app_id, pk, org, inst_id)
    return _github_app


def set_github_app(app: GitHubApp) -> None:
    """Override the GitHubApp instance (for testing)."""
    global _github_app
    _github_app = app
