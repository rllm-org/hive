---
name: hive
description: Run the hive experiment loop — autonomous iteration on a shared task.
argument-hint: "[OWNER/SLUG]"
---

EXECUTE IMMEDIATELY — start the experiment loop.

## Preflight

1. Check we're in a hive task directory: `cat .hive/task 2>/dev/null`
2. If not in a task directory and an `OWNER/SLUG` task ref was provided via $ARGUMENTS, the local clone directory uses the slug only — try `cd <slug>` (the part after the `/`).
3. If still no `.hive/task`, tell user to run `/hive-setup` first and stop

## Execution

1. Read the loop skill: `.claude/skills/hive/SKILL.md`
2. Read `program.md` for task-specific constraints
3. Execute the experiment loop as defined in the skill
4. Never stop. Never ask to continue.
