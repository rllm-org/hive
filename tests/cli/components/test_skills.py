from hive.cli.components.skills import print_skills_list, print_skill_detail


def test_print_skills_list(capsys):
    skills = [{"id": 1, "name": "chain-of-thought", "score_delta": 0.05,
               "description": "Use CoT prompting"}]
    print_skills_list(skills)
    out = capsys.readouterr().out
    assert "chain-of-thought" in out
    assert "+0.050" in out


def test_print_skill_detail(capsys):
    skill = {"id": 1, "name": "cot", "score_delta": 0.1,
             "description": "Chain of thought", "code_snippet": "print('hello')"}
    print_skill_detail(skill)
    out = capsys.readouterr().out
    assert "cot" in out
    assert "print('hello')" in out


def test_print_skill_detail_no_code(capsys):
    skill = {"id": 2, "name": "empty", "score_delta": None,
             "description": "No code", "code_snippet": ""}
    print_skill_detail(skill)
    out = capsys.readouterr().out
    assert "empty" in out
