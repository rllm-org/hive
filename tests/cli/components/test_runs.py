from hive.cli.components.runs import print_leaderboard, print_run_table, print_run_detail


def test_print_leaderboard_empty(capsys):
    print_leaderboard([])
    out = capsys.readouterr().out
    assert "No runs yet" in out


def test_print_leaderboard(capsys):
    entries = [{"id": "abc12345", "score": 0.95, "agent_id": "agent-1",
                "tldr": "good run", "verified": False}]
    print_leaderboard(entries)
    out = capsys.readouterr().out
    assert "0.9500" in out
    assert "agent-1" in out


def test_print_run_table_best_runs(capsys):
    data = {"runs": [{"id": "sha12345678", "score": 0.9, "verified": True,
                       "agent_id": "a1", "tldr": "first"}]}
    print_run_table(data, "best_runs")
    out = capsys.readouterr().out
    assert "a1" in out
    assert "0.9000" in out


def test_print_run_table_contributors(capsys):
    data = {"entries": [{"agent_id": "a1", "total_runs": 5, "best_score": 0.9}]}
    print_run_table(data, "contributors")
    out = capsys.readouterr().out
    assert "a1" in out


def test_print_run_table_deltas(capsys):
    data = {"entries": [{"run_id": "sha12345678", "delta": 0.05,
                          "from_score": 0.85, "to_score": 0.9, "agent_id": "a1"}]}
    print_run_table(data, "deltas")
    out = capsys.readouterr().out
    assert "a1" in out


def test_print_run_table_improvers(capsys):
    data = {"entries": [{"agent_id": "a1", "improvements_to_best": 3, "best_score": 0.9}]}
    print_run_table(data, "improvers")
    out = capsys.readouterr().out
    assert "a1" in out


def test_print_run_detail(capsys):
    r = {"id": "abc123", "agent_id": "agent-1", "repo_url": "https://github.com/test",
         "branch": "main", "score": 0.95, "verified": False, "tldr": "test run"}
    print_run_detail(r)
    out = capsys.readouterr().out
    assert "agent-1" in out
    assert "0.950" in out
