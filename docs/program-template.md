# program.md Template

Use this as the starting point for the `program.md` file in any new hive task repo.

Replace all `<placeholders>` with task-specific content.

---

```markdown
# <Task Name> Solver

<One-line description of the task.>

## Setup

1. **Read the in-scope files**: The repo is small. Read these files for full context:
   - `agent.py` — the file you modify. <Brief description of what the agent does>.
   - `eval/eval.sh` — runs evaluation. Do not modify.
   - `prepare.sh` — downloads the dataset. Do not modify.
2. **Run prepare**: `bash prepare.sh` to download the dataset.
3. **Verify data exists**: Check that `data/` contains `test.jsonl`. If not, run `bash prepare.sh`.
4. **Initialize results.tsv**: Create `results.tsv` with just the header row.
5. **Run baseline**: `bash eval/eval.sh` to establish the starting accuracy.

## The benchmark

<Describe what the benchmark tests. What does each problem look like? What categories or domains does it cover? What makes it challenging?>

Total: **<N> test problems**. <Brief description of input/output format.>

## Experimentation

**What you CAN do:**
- Modify `agent.py` — this is the only file you edit. Everything is fair game: <list relevant strategies for this task type, e.g. prompting strategy, few-shot examples, chain-of-thought, self-verification, answer extraction, retry logic>.

**What you CANNOT do:**
- Modify `eval/`, `prepare.sh`, or test data.
- Change the model. The model is fixed (set via `SOLVER_MODEL` env var).
- Install new packages beyond what's in `requirements.txt`.

**The goal: maximize <metric>.** <Describe what counts as correct and how accuracy is computed. E.g. "A problem passes when the generated code executes all test assertions without error. Accuracy = fraction of problems that pass.">

**Cost** is a soft constraint. Some increase in API calls is acceptable for meaningful accuracy gains, but prefer single-pass solutions.

**Simplicity criterion**: All else being equal, simpler is better. A small improvement that adds ugly complexity is not worth it.

**The first run**: Always establish the baseline first by running the eval as-is.

## Output format

The eval prints a summary:

```
---
accuracy:         <example_score>
correct:          <example_correct>
total:            <N>
```

You can extract the key metric:

```
grep "^accuracy:" run.log
```

## Logging results

Log each experiment to `results.tsv` (tab-separated):

```
commit	accuracy	cost_usd	status	description
a1b2c3d	<score>	0.42	keep	baseline
b2c3d4e	<score>	0.50	keep	<what you tried>
c3d4e5f	<score>	0.90	discard	<what you tried> (no gain, 2x cost)
d4e5f6g	0.000000	0.00	crash	<what broke>
```

## The experiment loop

LOOP FOREVER:

1. **THINK** — decide what to try next. This is the most important step. Review your results.tsv, think about what worked and what didn't, form a hypothesis for your next experiment.
2. Modify `agent.py` with your experimental idea.
3. git commit
4. Run the experiment: `bash eval/eval.sh > run.log 2>&1`
5. Read out the results: `grep "^accuracy:" run.log`
6. If the grep output is empty, the run crashed. Run `tail -n 50 run.log` for the stack trace and attempt a fix.
7. Record the results in results.tsv (do not commit results.tsv).
8. If accuracy improved (higher), keep the git commit. If equal or worse, `git reset --hard HEAD~1`.

**Timeout**: If a run exceeds <30 or 60> minutes, kill it and treat it as a failure.

**Crashes**: If it's a dumb fix (typo, bad format), fix and re-run. If fundamentally broken, skip it.

**NEVER STOP**: Once the loop begins, do NOT pause to ask the human. The human might be asleep. You are autonomous. If you run out of ideas, think harder — try combining previous near-misses, try more radical prompting strategies, read the code for new angles. The loop runs until interrupted.
```
