from hive.cli.components.chat import print_channel_list, print_history, print_thread


def test_print_channel_list(capsys):
    print_channel_list([
        {"name": "general", "is_default": True},
        {"name": "ideas", "is_default": False},
    ])
    out = capsys.readouterr().out
    assert "general" in out
    assert "ideas" in out


def test_print_channel_list_empty(capsys):
    print_channel_list([])
    out = capsys.readouterr().out
    assert "No channels" in out


def test_print_history(capsys):
    msgs = [
        {"ts": "1.000000", "agent_id": "swift-fox", "text": "hello",
         "created_at": "2026-04-07T12:00:00+00:00", "reply_count": 0},
        {"ts": "2.000000", "agent_id": "quiet-owl", "text": "hi back",
         "created_at": "2026-04-07T12:01:00+00:00", "reply_count": 2},
    ]
    print_history("general", msgs)
    out = capsys.readouterr().out
    assert "general" in out
    assert "swift-fox" in out
    assert "hello" in out
    assert "hi back" in out
    assert "2 replies" in out


def test_print_history_empty(capsys):
    print_history("general", [])
    out = capsys.readouterr().out
    assert "No messages" in out


def test_print_thread(capsys):
    parent = {"ts": "1.0", "agent_id": "a", "text": "parent",
              "created_at": "2026-04-07T12:00:00+00:00", "reply_count": 1}
    replies = [{"ts": "2.0", "agent_id": "b", "text": "reply",
                "created_at": "2026-04-07T12:01:00+00:00", "reply_count": 0}]
    print_thread("general", parent, replies)
    out = capsys.readouterr().out
    assert "parent" in out
    assert "reply" in out


def test_print_thread_no_replies(capsys):
    parent = {"ts": "1.0", "agent_id": "a", "text": "parent",
              "created_at": "2026-04-07T12:00:00+00:00", "reply_count": 0}
    print_thread("general", parent, [])
    out = capsys.readouterr().out
    assert "No replies" in out
