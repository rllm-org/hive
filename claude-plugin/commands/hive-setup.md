---
name: hive-setup
description: Install hive-evolve, register an agent, clone a task, and prepare the environment. Interactive setup wizard.
argument-hint: "[--server URL] [--name NAME] [OWNER/SLUG]"
---

EXECUTE IMMEDIATELY — run the setup wizard.

## Argument Parsing

Extract from $ARGUMENTS if provided:
- `--server <url>` or `server:` — hive server URL (optional, has default)
- `--name <name>` or `name:` — preferred agent name (optional)
- Positional argument — task ref to clone in `OWNER/SLUG` format, e.g. `hive/gsm8k-solver` (public) or `alice/my-task` (private). Optional; will ask if not provided.

## Execution

1. Read the setup skill: `.claude/skills/hive-setup/SKILL.md`
2. If a task ref provided in arguments, carry it through to Step 4/5 (skip task selection question)
3. If server URL provided, carry it through to Step 2 (skip server question)
4. If name provided, carry it through to Step 2 (skip name question)
5. Execute all steps in order, using `AskUserQuestion` for any missing inputs
