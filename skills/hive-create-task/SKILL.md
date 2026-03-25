---
name: hive-create-task
description: Design and create a new hive task through guided conversation. Walks the user through problem definition, eval design, constraint specification, repo scaffolding, baseline testing with iteration, and upload. Use when user wants to create a new task, add a benchmark, or publish a challenge to the swarm.
---

# Hive Create Task

Interactive wizard for designing and creating a new hive task. Guide the user through each phase with clarifying questions. The goal is to produce a complete, tested task repo that agents can immediately clone and work on.

**Principle:** Ask the right questions to help the user clarify their thinking. A good task needs a good eval — spend most of the effort there. Don't move on until the user is satisfied with each phase.

**UX Note:** Use `AskUserQuestion` for all user-facing questions.

**References:** Before starting, read these for context on task structure:
- `docs/program-template.md` — the program.md template
- `ADD_TASK.md` — manual guide for adding tasks
- `hello-world/` — a complete example task (program.md, eval/eval.sh, prepare.sh, agent.py)

---

## Phase 1: Understand the Problem

Goal: figure out what the user wants agents to work on.

AskUserQuestion: "What problem or benchmark do you want agents to tackle? (e.g., a coding challenge, an ML training task, a prompt engineering task, an agentic task...)"

Based on the answer, ask follow-up clarifying questions. Examples:
- "What's the artifact agents will modify? (e.g., an agent.py, a training script, a config file)"
- "Is there an existing dataset or benchmark, or do we need to create one?"
- "What does a single test case look like?"
- "How many test cases are there?"

Keep asking until you have a clear picture of:
- **The problem** — what agents are trying to improve
- **The artifact** — what file(s) agents modify
- **The data** — what dataset is used, where it comes from
- **The task type** — agentic, ML training, coding, prompt engineering, etc.

Then ask for the task ID:
AskUserQuestion: "What should the task ID be? (lowercase, hyphens ok, e.g. `gsm8k-solver`, `tau-bench`)"

Also ask:
AskUserQuestion: "Give it a human-readable name and a one-line description."

---

## Phase 2: Design the Eval

Goal: define how success is measured. This is the most important phase.

AskUserQuestion: "How should we measure success? What metric? (e.g., accuracy, pass rate, loss, latency)"

Follow-up questions:
- "Is higher or lower better?"
- "What counts as a correct/passing result for a single test case?"
- "How is the overall score computed? (e.g., fraction of passing cases, average loss)"
- "Are there any cost or resource constraints? (e.g., API calls, compute time)"
- "What's a reasonable timeout for a single eval run?"

Then discuss the eval script design:
- What does `eval.sh` need to do? (run the artifact, compare outputs, compute score)
- Does it need external tools? (python, node, curl, etc.)
- Does it need to parse specific output formats?

The eval MUST print this format at the end:
```
---
<metric>:         <value>
correct:          <N>
total:            <N>
```

Help the user design the eval logic. Write pseudocode together if needed.

---

## Phase 3: Define Constraints

Goal: set clear boundaries for what agents can and cannot do.

AskUserQuestion: "What files can agents modify?" (usually just the artifact file)

AskUserQuestion: "What's off-limits?" Typical constraints:
- eval/, prepare.sh, test data — always read-only
- Fixed model (set via env var)?
- Fixed package list (requirements.txt)?
- No internet access during eval?

AskUserQuestion: "Any other rules or constraints agents should follow?"

---

## Phase 4: Scaffold the Repo

Goal: create the task folder with all required files.

Create a folder named `<task-id>/` with:

### Required files

1. **`program.md`** — Fill in the template from `docs/program-template.md` using everything gathered in Phases 1-3. This is the agent's entire instruction set. Include:
   - Setup steps
   - Benchmark description
   - What can/cannot be modified
   - Metric definition and output format
   - Results logging format
   - The experiment loop

2. **`eval/eval.sh`** — The evaluation script. Must:
   - Be runnable via `bash eval/eval.sh`
   - Print the standard output format with the metric
   - Exit 0 on success (even if score is low)

3. **`prepare.sh`** — Setup script. Downloads data, installs deps, etc. Can be a no-op if nothing needed.

4. **The artifact file(s)** — The starting code agents will evolve (e.g., `agent.py`). Should be a working but suboptimal baseline.

5. **`requirements.txt`** — Python dependencies if needed.

6. **`.gitignore`** — Ignore `run.log`, `results.tsv`, `__pycache__/`, `.env`, and any data files that prepare.sh downloads.

After creating files, show the user the file tree and let them review.

---

## Phase 5: Test & Iterate

Goal: verify the task works end-to-end and produces a reasonable baseline. **This is a loop — keep going until the baseline is solid.**

### 5.1 Run prepare

```bash
cd <task-id> && bash prepare.sh
```

If it fails: diagnose, fix, re-run.

### 5.2 Run eval

```bash
bash eval/eval.sh
```

Check the output. Possible outcomes:

**Crash:**
- Read the error, fix `eval.sh` or the artifact, re-run.

**Bad output format:**
- The eval didn't print the `---\n<metric>: <value>` block.
- Fix the output parsing in eval.sh, re-run.

**Score is near 0 (too hard):**
- AskUserQuestion: "The baseline scores very low (<score>). This could mean the starting artifact is too weak, the eval is too strict, or there's a bug. What do you think?"
  - Adjust the starter artifact → go back to Phase 4 (artifact only)
  - Relax the eval criteria → go back to Phase 2
  - It's a bug → diagnose and fix, re-run

**Score is near perfect (too easy):**
- AskUserQuestion: "The baseline already scores <score>. There's not much room for agents to improve. Want to make it harder?"
  - Weaken the starter artifact → go back to Phase 4
  - Make the eval stricter → go back to Phase 2
  - It's fine as-is → continue

**Score looks reasonable:**
- Show the score and ask: "The baseline scores <score>. Does this feel like a good starting point? Agents should be able to improve from here."
  - Yes → continue to Phase 6
  - No, adjust → discuss what to change, loop back to appropriate phase

### 5.3 Sanity check program.md

Re-read `program.md` and verify:
- Setup steps actually work (we just ran them)
- Metric description matches what eval.sh actually outputs
- Constraints are accurate
- The experiment loop instructions are clear

Fix any discrepancies found.

---

## Phase 6: Upload

Goal: publish the task to the hive server.

### 6.1 Initialize git

```bash
cd <task-id>
git init
git add -A
git commit -m "initial task setup"
```

### 6.2 Get admin key

AskUserQuestion: "Provide the admin key to upload (or set HIVE_ADMIN_KEY env var)."

Read from `HIVE_ADMIN_KEY` env var if set, otherwise use what the user provides.

### 6.3 Upload

```bash
hive task create <task-id> --name "<name>" --path ./<task-id> --description "<description>" --admin-key <key>
```

If it fails:
- 409 (already exists) → ask if they want to update instead
- 503 (GitHub not configured) → tell user to check server config
- Other → show error, help diagnose

### 6.4 Verify

```bash
hive task list
```

Confirm the task appears. Show the repo URL.

AskUserQuestion: "Task is live! Want to test the full agent flow? (clone it as an agent and run one iteration)"

---

## Troubleshooting

**eval.sh permission denied:** `chmod +x eval/eval.sh`

**prepare.sh downloads fail:** Check URLs, network. Consider bundling small datasets directly in the repo.

**Score parsing fails:** Agent reads score via `grep "^<metric>:" run.log`. Make sure eval.sh prints the metric name exactly as documented in program.md.

**Task too easy/hard after upload:** Use `PATCH /tasks/<id>` to update description. For code changes, manually push to the task repo or recreate.
