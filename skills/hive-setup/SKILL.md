---
name: hive-setup
description: Install hive-evolve, register an agent, clone a task, and prepare the environment. Use when user wants to set up hive, join a swarm, or get started with a task. Triggers on "setup hive", "join hive", "hive setup", or first-time hive requests.
---

# Hive Setup

Interactive setup wizard. Walk the user through each step, asking questions where needed. Only pause when user input is required (server URL, agent name, task selection). Fix problems yourself when possible.

**Principle:** When something is broken or missing, fix it. Don't tell the user to go fix it themselves unless it genuinely requires their action (e.g. choosing a server, picking a task). If a dependency is missing, install it. If a command fails, diagnose and repair.

**UX Note:** Use `AskUserQuestion` for all user-facing questions.

## 0. Preflight

Check if `hive` is already installed:
- `which hive && hive --version`

**If not found:** Continue to Step 1.
**If found:** Skip to Step 2.

## 1. Install / Update

Check Python environment:
- `python3 --version`

If Python not found or < 3.10:
- AskUserQuestion: "Python 3.10+ is required. Would you like me to install it?"
- macOS: `brew install python@3.12`
- Linux: `sudo apt-get install -y python3 python3-pip`

Install hive-evolve as a global CLI tool (no venv activation needed):
- If `uv` available: `uv tool install hive-evolve`
- Else if `pipx` available: `pipx install hive-evolve`
- Else if `pip` available: `pip install hive-evolve`
- Else: install uv first: `curl -LsSf https://astral.sh/uv/install.sh | sh`, then `uv tool install hive-evolve`

If already installed, upgrade:
- `uv tool upgrade hive-evolve` or `pipx upgrade hive-evolve`

Verify:
- `hive --version`

If verification fails, read the error and fix (common: PATH issue, venv not activated).

## 2. Register Agent

First check if an agent is already registered:
- `hive auth whoami`

**If whoami succeeds (returns agent name):**
- AskUserQuestion: "You're already registered as `<agent_name>`. Use this identity?"
  - Yes → skip to Step 3
  - No, register a new one → continue below

**Server URL:**
AskUserQuestion: "Use the default hive server, or do you have a specific server URL?"
- Default → use the production server URL
- Custom → ask for the URL

**Agent name:**
AskUserQuestion: "How would you like to name your agent?"
- Pick my own → ask for the name
- Generate a cool name for me → generate a creative two-word name (e.g. "phantom-volt", "neon-sphinx", "arctic-forge") and confirm with user
- Let the server decide → leave blank, server auto-generates

Run:
- `hive auth register --server <url> --name <name>`

If name is taken, the server auto-generates one. Show the assigned name:
- `hive auth whoami`

If registration fails:
- Connection refused → server might be down, ask user to verify the URL
- 4xx error → parse error message, show to user

## 3. Select Task

Show available tasks:
- `hive task list`

If no tasks: tell user the server has no tasks yet, stop.

If one task: AskUserQuestion: "There's one task available: `<name>` — `<description>`. Clone it?"

If multiple tasks: AskUserQuestion with task list, let user pick.

## 4. Clone Task

Run:
- `hive task clone <task-id>`

**Public tasks:** Creates a fork repo with a deploy key and clones via SSH.
**Private tasks:** Clones the repo with a read-only deploy key and checks out a `hive/<agent>/initial` branch.

If clone fails:
- SSH key error → check `~/.hive/keys/` permissions, ensure key file is `chmod 600`
- Network error → retry once, then ask user
- "Install the Hive GitHub App" error → the repo owner needs to install the GitHub App first
- Already cloned (directory exists) → AskUserQuestion: "Directory `<task-id>/` already exists. Use it or re-clone?"

After clone, cd into the task directory:
- `cd <task-id>`

## 5. Prepare Environment

Check for `prepare.sh`:
- `test -f prepare.sh && echo "found" || echo "not found"`

If found:
- Tell user: "Running prepare.sh to set up data/environment..."
- `bash prepare.sh`
- If it fails, show the last 30 lines of output and diagnose

Check for `requirements.txt`:
- `test -f requirements.txt && echo "found" || echo "not found"`

If found:
- `uv pip install -r requirements.txt` or `pip install -r requirements.txt`

## 6. Verify

Run a quick check that everything works:
- `hive auth whoami` — agent identity OK
- `hive task context` — can reach server, task is accessible
- Check eval exists: `test -f eval/eval.sh`
- Check data exists (if prepare.sh was run)

Show summary:
- Agent name
- Server URL
- Task ID
- Task mode (check `.hive/fork.json` → `mode` field: "fork" or "branch")
- Key files present (program.md, eval/eval.sh, prepare.sh)

Tell user: "Always use `hive push` to push code (not `git push`). It works for both public and private tasks."

AskUserQuestion: "Setup complete. Start the experiment loop now?"
- Yes → invoke `/hive`
- No → tell user: "You can start the experiment loop anytime by running `/hive`."

## Troubleshooting

**hive command not found after install:** PATH issue. Check `which hive`, try `python3 -m hive` as fallback. If using uv, ensure the venv is activated or install globally.

**SSH clone fails ("Permission denied"):** The deploy key might not have been saved correctly. Check `~/.hive/keys/<fork-name>` exists and has mode 600. Re-run `hive task clone` (idempotent — won't return the key again on second call, but the key should already be saved).

**Server connection refused:** Verify the URL is correct and includes the protocol (https://). Check if `HIVE_SERVER` env var conflicts with `--server` flag.

**prepare.sh fails:** Read the error output. Common causes: missing system dependencies (curl, wget, unzip), disk space, network issues downloading datasets.
