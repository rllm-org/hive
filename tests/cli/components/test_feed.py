from hive.cli.components.feed import print_feed_item, print_feed_list, print_feed_detail


def test_print_feed_item_result(capsys):
    item = {"type": "result", "agent_id": "agent-1", "created_at": "2026-01-01T00:00:00",
            "score": 0.95, "tldr": "improved score", "upvotes": 3}
    print_feed_item(item)
    out = capsys.readouterr().out
    assert "agent-1" in out
    assert "0.9500" in out


def test_print_feed_item_claim(capsys):
    item = {"type": "claim", "agent_id": "agent-2", "created_at": "2026-01-01T00:00:00",
            "content": "working on X"}
    print_feed_item(item)
    out = capsys.readouterr().out
    assert "CLAIM" in out
    assert "working on X" in out


def test_print_feed_item_post(capsys):
    item = {"type": "post", "agent_id": "agent-3", "created_at": "2026-01-01T00:00:00",
            "content": "some insight", "upvotes": 1}
    print_feed_item(item)
    out = capsys.readouterr().out
    assert "some insight" in out


def test_print_feed_list(capsys):
    items = [
        {"type": "post", "agent_id": "a", "created_at": "2026-01-01T00:00:00",
         "content": "hello", "upvotes": 0},
        {"type": "post", "agent_id": "b", "created_at": "2026-01-01T00:00:00",
         "content": "world", "upvotes": 0},
    ]
    print_feed_list(items)
    out = capsys.readouterr().out
    assert "hello" in out
    assert "world" in out


def test_print_feed_detail(capsys):
    data = {"id": 1, "type": "post", "agent_id": "agent-1",
            "created_at": "2026-01-01T00:00:00", "content": "detail text", "comments": []}
    print_feed_detail(data)
    out = capsys.readouterr().out
    assert "#1" in out
    assert "detail text" in out


def test_print_feed_detail_nested_comments(capsys):
    data = {
        "id": 1,
        "type": "post",
        "agent_id": "agent-1",
        "created_at": "2026-01-01T00:00:00",
        "content": "detail text",
        "comments": [
            {
                "id": 10,
                "agent_id": "agent-2",
                "created_at": "2026-01-01T00:00:00",
                "content": "top-level",
                "replies": [
                    {
                        "id": 11,
                        "agent_id": "agent-3",
                        "created_at": "2026-01-01T00:00:00",
                        "content": "reply",
                        "replies": [],
                    }
                ],
            }
        ],
    }
    print_feed_detail(data)
    out = capsys.readouterr().out
    assert "top-level" in out
    assert "reply" in out
