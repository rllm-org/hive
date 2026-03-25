---
name: hive-create-task
description: Design and create a new hive task through guided conversation. Interactive wizard.
argument-hint: "[TASK_ID]"
---

EXECUTE IMMEDIATELY — start the task creation wizard.

## Argument Parsing

Extract from $ARGUMENTS if provided:
- Positional argument — task ID (optional, will ask if not provided)

## Execution

1. Read the skill: `.claude/skills/hive-create-task/SKILL.md`
2. If task ID provided in arguments, carry it through to Phase 1 (skip task ID question)
3. Execute all phases in order, using `AskUserQuestion` for all user-facing questions
