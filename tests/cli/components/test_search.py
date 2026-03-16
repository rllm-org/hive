from hive.cli.components.search import print_search_results


def test_print_search_results(capsys):
    results = [
        {"id": 1, "type": "post", "agent_id": "agent-1",
         "created_at": "2026-01-01T00:00:00", "content": "some insight"},
        {"id": 2, "type": "result", "agent_id": "agent-2",
         "created_at": "2026-01-01T00:00:00", "score": 0.95, "tldr": "good run"},
    ]
    print_search_results(results)
    out = capsys.readouterr().out
    assert "agent-1" in out
    assert "agent-2" in out
    assert "hive feed view" in out


def test_print_search_results_claim(capsys):
    results = [{"id": 3, "type": "claim", "agent_id": "a",
                "created_at": "2026-01-01T00:00:00", "content": "working on X"}]
    print_search_results(results)
    out = capsys.readouterr().out
    assert "working on X" in out


def test_print_search_results_skill(capsys):
    results = [{"id": 4, "type": "skill", "agent_id": "a",
                "created_at": "2026-01-01T00:00:00", "name": "cot",
                "description": "Chain of thought"}]
    print_search_results(results)
    out = capsys.readouterr().out
    assert "cot" in out
