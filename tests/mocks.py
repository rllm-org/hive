class MockGitHubApp:
    """Mock GitHubApp for tests."""

    def __init__(self, org="hive-agents"):
        self.org = org
        self.created_repos = []
        self.deleted_repos = []
        self.deploy_keys = []
        self._key_counter = 100

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

    def add_deploy_key(self, repo_full_name: str, title: str, public_key: str) -> int:
        self._key_counter += 1
        self.deploy_keys.append((repo_full_name, title, public_key, self._key_counter))
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
