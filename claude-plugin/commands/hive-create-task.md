---
name: hive-create-task
description: Design and create a new hive task through guided conversation. Interactive wizard.
argument-hint: "[SLUG]"
---

EXECUTE IMMEDIATELY — start the task creation wizard.

## Argument Parsing

Extract from $ARGUMENTS if provided:
- Positional argument — task slug (optional, will ask if not provided). The slug is the short identifier that will appear in `/task/hive/<slug>` (public) or `/task/<your-handle>/<slug>` (private).

## Execution

1. Read the skill: `.claude/skills/hive-create-task/SKILL.md`
2. If a slug was provided in arguments, carry it through to Phase 1 (skip the slug question)
3. Execute all phases in order, using `AskUserQuestion` for all user-facing questions
