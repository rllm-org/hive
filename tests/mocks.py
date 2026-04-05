class MockGitHubApp:
    """Mock GitHubApp for tests."""

    def __init__(self, org="hive-agents"):
        self.org = org
        self.created_repos = []
        self.deleted_repos = []
        self.deploy_keys = []
        self.pushed_branches = []
        self.created_branches = []
        self._key_counter = 100
        self._install_token_cache: dict[str, tuple[str, int]] = {}
        # Map repo_full_name -> installation_id (set in tests to simulate App installation)
        self._repo_installations: dict[str, str] = {}

    def get_token(self) -> str:
        return "MOCK_TOKEN"

    def headers(self) -> dict:
        return {"Authorization": "Bearer MOCK_TOKEN"}

    def clone_url(self, repo_name: str) -> str:
        return f"https://x-access-token:MOCK_TOKEN@github.com/{self.org}/{repo_name}.git"

    def copy_repo(self, source_url: str, repo_name: str) -> dict:
        self.created_repos.append((source_url, repo_name))
        return {
            "html_url": f"https://github.com/{self.org}/{repo_name}",
            "ssh_url": f"git@github.com:{self.org}/{repo_name}.git",
            "base_sha": "mock-base-sha",
        }

    def add_deploy_key(self, repo_full_name: str, title: str, public_key: str,
                       read_only: bool = False) -> int:
        self._key_counter += 1
        self.deploy_keys.append((repo_full_name, title, public_key, self._key_counter, read_only))
        return self._key_counter

    def remove_deploy_key(self, repo_full_name: str, key_id: int) -> None:
        pass

    def delete_repo(self, repo_full_name: str) -> None:
        self.deleted_repos.append(repo_full_name)

    def set_branch_protection(self, repo_full_name: str, branch: str, lock: bool = False) -> None:
        pass

    def create_task_repo(self, task_id: str, archive_bytes: bytes, description: str = "") -> str:
        repo_name = f"task--{task_id}"
        self.created_repos.append((repo_name, description))
        return f"https://github.com/{self.org}/{repo_name}"

    def generate_ssh_keypair(self) -> tuple[str, str]:
        return ("MOCK_PRIVATE_KEY", "ssh-ed25519 MOCK_PUBLIC_KEY mock")

    # --- Multi-installation support (for private tasks) ---

    def get_token_for_installation(self, installation_id: str) -> str:
        return f"MOCK_TOKEN_{installation_id}"

    def get_repo_installation_id(self, repo_full_name: str) -> str | None:
        return self._repo_installations.get(repo_full_name)

    def headers_for_installation(self, installation_id: str) -> dict:
        return {"Authorization": f"Bearer MOCK_TOKEN_{installation_id}"}

    def get_repo_ssh_url(self, repo_full_name: str, installation_id: str) -> str:
        return f"git@github.com:{repo_full_name}.git"

    def add_deploy_key_for_installation(self, repo_full_name: str, title: str,
                                         public_key: str, installation_id: str,
                                         read_only: bool = False) -> int:
        return self.add_deploy_key(repo_full_name, title, public_key, read_only)

    def create_branch(self, repo_full_name: str, branch: str,
                      from_branch: str, installation_id: str) -> None:
        self.created_branches.append((repo_full_name, branch, from_branch))

    def set_branch_protection_for_installation(self, repo_full_name: str, branch: str,
                                                installation_id: str) -> None:
        pass

    def push_branch(self, repo_full_name: str, installation_id: str,
                    bundle_path: str, branch: str) -> None:
        self.pushed_branches.append((repo_full_name, branch, bundle_path))
