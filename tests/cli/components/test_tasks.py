from hive.cli.components.tasks import print_task_table, print_clone_instructions, print_context


def test_print_task_table(capsys):
    tasks = [{"id": 1, "owner": "hive", "slug": "gsm8k", "name": "GSM8K Solver",
              "stats": {"best_score": 0.95, "total_runs": 10, "agents_contributing": 3}}]
    print_task_table(tasks)
    out = capsys.readouterr().out
    assert "hive/gsm8k" in out
    assert "GSM8K Solver" in out


def test_print_clone_instructions(capsys):
    print_clone_instructions("gsm8k", "my-agent")
    out = capsys.readouterr().out
    assert "gsm8k" in out
    assert "program.md" in out


def test_print_context(capsys):
    data = {
        "task": {"name": "GSM8K", "description": "Math", "stats": {
            "total_runs": 5, "improvements": 2, "agents_contributing": 3}},
        "leaderboard": [],
        "active_claims": [],
        "feed": [],
        "skills": [],
    }
    print_context(data, "gsm8k")
    out = capsys.readouterr().out
    assert "GSM8K" in out
    assert "No runs yet" in out
