import json
import subprocess
from pathlib import Path

import click.testing

from hive.cli.hive import hive
from hive.cli.cmd_swarm import _clone_one


class TestSwarmHelp:
    def test_swarm_help(self):
        runner = click.testing.CliRunner()
        result = runner.invoke(hive, ["swarm", "--help"])
        assert result.exit_code == 0
        assert "swarm" in result.output.lower()


class TestSwarmStatus:
    def test_no_swarms(self, tmp_path, monkeypatch):
        monkeypatch.setattr("hive.cli.swarm_state.SWARMS_DIR", tmp_path / "swarms")
        runner = click.testing.CliRunner()
        result = runner.invoke(hive, ["swarm", "status"])
        assert result.exit_code == 0
        assert "No active swarms" in result.output

    def test_unknown_task(self, tmp_path, monkeypatch):
        monkeypatch.setattr("hive.cli.swarm_state.SWARMS_DIR", tmp_path / "swarms")
        runner = click.testing.CliRunner()
        result = runner.invoke(hive, ["swarm", "status", "no-such-task"])
        assert result.exit_code != 0


class TestSwarmStop:
    def test_no_swarms(self, tmp_path, monkeypatch):
        monkeypatch.setattr("hive.cli.swarm_state.SWARMS_DIR", tmp_path / "swarms")
        runner = click.testing.CliRunner()
        result = runner.invoke(hive, ["swarm", "stop"])
        assert result.exit_code == 0


class TestSwarmDown:
    def test_unknown_task(self, tmp_path, monkeypatch):
        monkeypatch.setattr("hive.cli.swarm_state.SWARMS_DIR", tmp_path / "swarms")
        runner = click.testing.CliRunner()
        result = runner.invoke(hive, ["swarm", "down", "no-such-task"])
        assert result.exit_code != 0


def _make_branch_response(agent_id: str):
    return {
        "mode": "branch",
        "ssh_url": "git@github.com:owner/task--foo.git",
        "private_key": f"PRIVATE_KEY_FOR_{agent_id}",
        "default_branch": f"hive/{agent_id}/initial",
        "branch_prefix": f"hive/{agent_id}/",
    }


def _mock_subprocess(monkeypatch, *, checkout_fails=False):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[0] == "git" and cmd[1] == "clone":
            Path(cmd[3]).mkdir(parents=True, exist_ok=True)
            (Path(cmd[3]) / ".git").mkdir(exist_ok=True)
            return subprocess.CompletedProcess(cmd, 0, "", "")
        if cmd[0] == "git" and "checkout" in cmd and checkout_fails and "-b" not in cmd:
            return subprocess.CompletedProcess(cmd, 1, "", "error: pathspec did not match")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr("subprocess.run", fake_run)
    return calls


class TestCloneOneBugs:

    def test_bug1_deploy_key_collision(self, tmp_path, monkeypatch):
        """Two agents with same ssh_url must get separate key files."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))

        responses = iter([_make_branch_response("agent-1"),
                          _make_branch_response("agent-2")])
        monkeypatch.setattr("hive.cli.cmd_swarm._api",
                            lambda *a, **kw: next(responses))
        _mock_subprocess(monkeypatch)

        base = tmp_path / "work"
        base.mkdir()
        _clone_one("test-task", {"id": "agent-1", "token": "t1"}, base)
        _clone_one("test-task", {"id": "agent-2", "token": "t2"}, base)

        key_dir = fake_home / ".hive" / "keys"
        key_files = sorted(p.name for p in key_dir.iterdir())
        assert len(key_files) == 2, f"Expected 2 key files, got {key_files}"
        keys = {p.name: p.read_text() for p in key_dir.iterdir()}
        assert len(set(keys.values())) == 2, "Keys have identical content"

    def test_bug2_metadata_survives_checkout(self, tmp_path, monkeypatch):
        """.hive/agent must contain correct agent_id after checkout."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
        monkeypatch.setattr("hive.cli.cmd_swarm._api",
                            lambda *a, **kw: _make_branch_response("agent-1"))

        def fake_run(cmd, **kwargs):
            if cmd[0] == "git" and cmd[1] == "clone":
                Path(cmd[3]).mkdir(parents=True, exist_ok=True)
                (Path(cmd[3]) / ".git").mkdir(exist_ok=True)
                return subprocess.CompletedProcess(cmd, 0, "", "")
            if cmd[0] == "git" and "checkout" in cmd and "-b" not in cmd:
                work_dir = Path(cmd[cmd.index("-C") + 1])
                hive_dir = work_dir / ".hive"
                if hive_dir.exists():
                    (hive_dir / "agent").write_text("stale-agent")
                return subprocess.CompletedProcess(cmd, 0, "", "")
            return subprocess.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr("subprocess.run", fake_run)

        base = tmp_path / "work"
        base.mkdir()
        result = _clone_one("test-task", {"id": "agent-1", "token": "t1"}, base)

        agent_file = Path(result["work_dir"]) / ".hive" / "agent"
        assert agent_file.read_text() == "agent-1"

    def test_bug2_gitignore_added(self, tmp_path, monkeypatch):
        """.hive/ should be in workspace .gitignore."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
        monkeypatch.setattr("hive.cli.cmd_swarm._api",
                            lambda *a, **kw: _make_branch_response("agent-1"))
        _mock_subprocess(monkeypatch)

        base = tmp_path / "work"
        base.mkdir()
        result = _clone_one("test-task", {"id": "agent-1", "token": "t1"}, base)

        gitignore = Path(result["work_dir"]) / ".gitignore"
        assert gitignore.exists(), ".gitignore not created"
        assert ".hive/" in gitignore.read_text()

    def test_bug3_checkout_fallback_on_missing_branch(self, tmp_path, monkeypatch):
        """If branch doesn't exist, fall back to checkout -b."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
        monkeypatch.setattr("hive.cli.cmd_swarm._api",
                            lambda *a, **kw: _make_branch_response("agent-1"))
        calls = _mock_subprocess(monkeypatch, checkout_fails=True)

        base = tmp_path / "work"
        base.mkdir()
        _clone_one("test-task", {"id": "agent-1", "token": "t1"}, base)

        checkout_cmds = [c for c in calls if c[0] == "git" and "checkout" in c]
        assert len(checkout_cmds) >= 2, f"Expected checkout fallback, got {checkout_cmds}"
        assert "-b" in checkout_cmds[1]


def _init_bare_repo(path):
    """Create a bare git repo with one commit (simulates a GitHub remote)."""
    subprocess.run(["git", "init", "--bare", str(path)], capture_output=True, check=True)
    # Clone it, add a commit, push back
    tmp_clone = path.parent / "tmp-clone"
    subprocess.run(["git", "clone", str(path), str(tmp_clone)], capture_output=True, check=True)
    (tmp_clone / "README.md").write_text("hello")
    subprocess.run(["git", "-C", str(tmp_clone), "add", "."], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(tmp_clone), "commit", "-m", "init"],
                   capture_output=True, check=True,
                   env={**__import__("os").environ,
                        "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "t@t",
                        "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "t@t"})
    subprocess.run(["git", "-C", str(tmp_clone), "push"], capture_output=True, check=True)
    import shutil
    shutil.rmtree(tmp_clone)


class TestCloneOneIntegration:
    """End-to-end test using real git repos (no subprocess mocking)."""

    def test_two_agents_private_task(self, tmp_path, monkeypatch):
        """Simulate two agents cloning the same private-task repo in branch mode."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))

        # Create a bare repo to act as the "remote"
        remote = tmp_path / "remote.git"
        _init_bare_repo(remote)

        call_count = 0
        agents = ["agent-alpha", "agent-beta"]

        def fake_api(*args, **kwargs):
            nonlocal call_count
            aid = agents[call_count]
            call_count += 1
            return {
                "mode": "branch",
                "ssh_url": str(remote),
                "private_key": f"KEY_{aid}",
                "default_branch": f"hive/{aid}/initial",
                "branch_prefix": f"hive/{aid}/",
            }

        monkeypatch.setattr("hive.cli.cmd_swarm._api", fake_api)

        base = tmp_path / "workdirs"
        base.mkdir()
        r1 = _clone_one("my-task", {"id": "agent-alpha", "token": "t1"}, base)
        r2 = _clone_one("my-task", {"id": "agent-beta", "token": "t2"}, base)

        # Bug 1: each agent has its own deploy key
        key_dir = fake_home / ".hive" / "keys"
        key_files = sorted(p.name for p in key_dir.iterdir())
        assert len(key_files) == 2
        assert "agent-alpha" in key_files[0]
        assert "agent-beta" in key_files[1]

        # Bug 2: .hive/agent is correct in each workspace
        assert (Path(r1["work_dir"]) / ".hive" / "agent").read_text() == "agent-alpha"
        assert (Path(r2["work_dir"]) / ".hive" / "agent").read_text() == "agent-beta"

        # Bug 2: .gitignore contains .hive/
        assert ".hive/" in (Path(r1["work_dir"]) / ".gitignore").read_text()
        assert ".hive/" in (Path(r2["work_dir"]) / ".gitignore").read_text()

        # Bug 2: fork.json has correct per-agent branch_prefix
        f1 = json.loads((Path(r1["work_dir"]) / ".hive" / "fork.json").read_text())
        f2 = json.loads((Path(r2["work_dir"]) / ".hive" / "fork.json").read_text())
        assert f1["branch_prefix"] == "hive/agent-alpha/"
        assert f2["branch_prefix"] == "hive/agent-beta/"

        # Bug 3: each agent is on its own branch (created via -b fallback)
        def current_branch(work_dir):
            r = subprocess.run(["git", "-C", work_dir, "branch", "--show-current"],
                               capture_output=True, text=True)
            return r.stdout.strip()

        assert current_branch(r1["work_dir"]) == "hive/agent-alpha/initial"
        assert current_branch(r2["work_dir"]) == "hive/agent-beta/initial"
