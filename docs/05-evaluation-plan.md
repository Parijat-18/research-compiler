# Evaluation Plan

**Companion to:** `01-PRD.md` (esp. §10).
**Purpose:** the protocol for proving the project's hypothesis — that compiled citation context improves Claude Code's paper-reproduction quality.

This is the document the project lives or dies on. The PRD describes what to build; this describes what would have to be true for the build to have been worth it.

---

## 1. Hypothesis (restated for evaluation)

> A Claude Code session given a target paper PLUS our compiled `research.md` and MCP query tools produces more faithful paper reproductions than a Claude Code session given only the target paper.

"More faithful" is operationalized along three axes:

- **Correctness:** rubric-graded subtask pass rate (PaperBench-style).
- **Coverage:** fraction of required implementation atoms actually implemented.
- **Hallucination rate:** fraction of implementation decisions that contradict the paper or its citation neighborhood.

We will measure all three.

---

## 2. Conditions

Three conditions, same model (Claude Code with the same underlying Claude version), same paper, same prompt.

| Condition | What the agent gets |
|---|---|
| **A — Baseline** | Target paper PDF (or arXiv link) only. No plugin installed. |
| **B — Brief only** | Plugin installed but `use-research-context` skill restricted to reading `research.md` and `missing-details.md`. MCP tools disabled. |
| **C — Full plugin** | Plugin installed with `research.md`, `missing-details.md`, AND MCP tools enabled. |

Condition B exists to separate the contribution of the written brief from the contribution of the queryable graph. Without it, we cannot tell whether the MCP tools are pulling weight.

---

## 3. Paper sample

### 3.1 v1 sample (development — 5 papers)

For internal iteration only. Pick 5 papers from different ML subareas that you understand well enough to grade by hand. Suggested mix:

- One vision contrastive-learning paper (clear architecture+loss+dataset chain).
- One LLM training paper (heavy on training tricks + scaling).
- One RLHF / alignment paper (clear method chain, contested implementation details).
- One graph-learning paper (different community, different parser surface).
- One classical-CV-meets-deep-learning paper (older citations, deeper neighborhood).

This is your dev set. Iterate the compiler against it. Don't use it for the final evaluation.

### 3.2 Final sample (evaluation — 20 papers)

Re-use the **PaperBench 20-paper set** if accessible. That gives us:

- A graded rubric already constructed (8,316 subtasks across 20 papers).
- A published baseline number (~21% with the best tested agent at PaperBench publication time) for triangulation.
- An audit trail anyone can verify.

If the PaperBench rubrics are not fully available, fall back to a **handcrafted 20-paper set** with rubrics built using the same methodology:

- Each paper decomposed into "leaf tasks" of the form "implement X with specification Y."
- Each leaf task gradable as `pass | partial | fail` with a clear rule.
- Target ~200–500 leaf tasks per paper.

In either case, freeze the sample and the rubric before running condition C. **No tuning the compiler on the final sample.**

---

## 4. Protocol per paper

For each paper × condition:

1. **Fresh repo.** Empty git repo, no prior state, no plugin remnants.
2. **Install plugin** if condition is B or C. Compile the paper (`/paper-compiler:build-research-context`). Save the compile time and `build-manifest.json`.
3. **Standardized implementation prompt** — same across conditions:

   > "Implement this paper end-to-end. Aim for a runnable repo that matches the paper's method as closely as possible. Where the paper is ambiguous, make a reasoned choice and document it. Don't run experiments — focus on faithful implementation."

4. **Bounded session.** Cap at 60 minutes wall time and 200 tool calls. Same caps across conditions.
5. **Save the session transcript and the final repo.**
6. **Grade.** Apply the rubric. For each leaf task: `pass | partial | fail | not_attempted`.

Repeat for each of the 20 papers, each of the 3 conditions = 60 runs.

---

## 5. Primary metrics

### 5.1 Replication score

Per paper × condition:

```
replication_score = (passes + 0.5 * partials) / total_rubric_items
```

Per condition, report:

- Mean across 20 papers.
- Median.
- 95% confidence interval (bootstrap, 10,000 resamples).
- Per-paper deltas vs. baseline (A).

**Target:** condition C – condition A ≥ +10 absolute percentage points on the mean.

### 5.2 Hallucination rate

For each session transcript, identify implementation decisions of the form "X is implemented as Y." For each decision, label whether Y is:

- **Supported:** paper or compiled brief contains evidence for Y.
- **Reasonable:** Y is a plausible default for an ambiguous detail, and the choice is made visible (commented or flagged).
- **Contradicted:** paper or compiled brief contains evidence against Y.
- **Fabricated:** Y is asserted with no support in either.

```
hallucination_rate = (contradicted + fabricated) / total_decisions
```

**Target:** condition C hallucination rate ≤ 50% of condition A rate.

### 5.3 Atom coverage

For each paper, the compiled `graph.json` enumerates the implementation atoms. After each run, check how many appear in the produced code (by name, by signature, or by structural match):

```
atom_coverage = atoms_present_in_code / atoms_in_brief
```

**Target:** condition C atom coverage ≥ 1.5× condition A coverage.

---

## 6. Secondary / diagnostic metrics

- **Compile coverage** — % of citation-neighborhood papers acquired and parsed. Diagnostic for the compiler; doesn't feed the headline result.
- **Classifier accuracy** — on a hand-labelled set of 300 edges (15 per paper across 20 papers), measured per role. Diagnostic.
- **MCP tool usage** — in condition C, how many tool calls per run, which tools are used most. Tells us which parts of the MCP surface are pulling weight.
- **Time-to-first-correct-component** — wall time from prompt to the first leaf task passing. Lower is better.
- **Cost** — total API tokens for the session. We want C to not be dramatically more expensive than A.

---

## 7. Grader design

Two graders:

1. **Automated grader.** A scoring script that runs each leaf-task check programmatically where possible (presence of a class/function with expected signature, presence of a config value, presence of a loop structure). Fast, cheap, deterministic.
2. **LLM grader.** For tasks the automated grader can't handle (semantic equivalence of math, qualitative architectural choices). Use a strong model, structured rubric prompts, temperature 0.

For 10% of leaf tasks (stratified random sample across papers, conditions, and difficulty), grade a **third time by hand**. Compute grader agreement (Cohen's kappa or simple agreement rate). If automated/LLM agreement with human is below 0.7, the rubric or the grader is broken — fix it before believing the headline numbers.

---

## 8. What "shipping" requires

A go/no-go decision based on this evaluation. Ship publicly if **all** of the following hold:

- **Δ (C – A) ≥ +10 percentage points** on mean replication score.
- **Δ (C – B) ≥ +3 percentage points** on mean replication score (the MCP tools are pulling weight beyond the brief).
- **Hallucination rate in C ≤ 50%** of A.
- **Atom coverage in C ≥ 1.5×** A.
- **Compile coverage ≥ 80%** of references resolved on average.
- **Grader human agreement ≥ 0.7** on the audited sample.

If we miss one of these by a small margin, iterate. If we miss two by significant margins, the design has a hole — go back to the architecture doc.

---

## 9. Failure-mode catalogue (to populate as we run)

Keep a living log of the failure modes we see across runs. For each, record:

- The paper.
- The condition where it appeared.
- A short description.
- Whether it represents a compiler bug, a classifier bug, a parser bug, a skill-prompt bug, or a fundamental hypothesis failure.

This log is the most valuable artifact the evaluation produces. The numbers tell you whether to ship; the log tells you what to do next.

Initial guesses at the failure modes we'll see:

- **Citation-context too short.** The paragraph around the citation doesn't carry enough signal for the classifier. The fix is broader windows, not a better classifier.
- **Math-heavy papers where TeX is the only viable parse.** PDFs lose equation structure. Mitigation: TeX-first, always, for arXiv papers.
- **Atoms the paper invents** that have no upstream citation. The brief should mark these clearly so Claude Code doesn't reach for a "defining paper" that doesn't exist.
- **Datasets behind login walls.** The brief can describe preprocessing but not actually let the agent download the data. We'll record this honestly.
- **Hyperparameter omissions.** Many papers don't list every hyperparameter. The brief should explicitly enumerate the ones the paper does list and mark the rest as assumptions.
- **Baselines as a rabbit hole.** Each baseline has its own citation neighborhood. The frontier policy should cap baseline expansion aggressively — we are reproducing the target, not the baselines.

---

## 10. Reporting

The eval produces three artifacts:

1. **A results table** — papers × conditions × metrics, plus aggregate rows.
2. **A failure-mode log** — annotated examples, one or two per paper.
3. **A write-up** — 5–10 pages, methodology + results + discussion. Internal first; consider public release as a short technical report alongside the v1 launch.

Reporting principles:

- Report all three conditions, not just A vs. C. If B closes most of the gap, that changes the story — the brief is doing the work, and the MCP surface is over-engineered.
- Report per-paper deltas, not just aggregates. A method that helps on 18/20 papers and hurts on 2 has a different story than one that helps uniformly.
- Report compute and dollar cost. The right comparison is "what does it cost to add 10 points of replication accuracy" — that frames the contribution honestly.

---

## 11. Reproducibility

The eval itself should be reproducible. Practically:

- Seed every LLM call we control (Claude Code's own calls are not fully seedable, which is fine — note it).
- Pin the model version, plugin version, and S2 dataset version.
- Commit the rubric. The rubric is part of the artifact.
- Publish (internally if not publicly) the compiled `research/` directories for each of the 20 papers. They are the inputs to condition C; a third party should be able to rerun condition C and broadly replicate.

---

## 12. When NOT to run this eval

Three preconditions before the eval is worth running:

1. The compiler compiles its own originating paper(s) end-to-end without manual intervention.
2. The atom coverage on the 5-paper dev set is ≥ 70%.
3. The classifier accuracy on the dev hand-labelled set is ≥ 75% per implementation-critical role.

If any of those are not true, the eval will measure noise. Iterate the compiler first.

---

## 13. The honest worst case

There is a version of this project where the headline metric moves by 3 points instead of 10, the brief helps but the MCP tools don't, and the hallucination rate barely budges. In that version:

- The brief is still useful — ship it.
- The MCP layer was overbuilt — quietly drop it from the default surface.
- The hypothesis is partially confirmed: citation context matters, but a written brief is enough.

That is a reasonable outcome and not a failure. Plan for it. Don't pretend the failure case is impossible.

The other worst case — the brief actively *hurts* the agent — is the one that would require a real rethink. If we see that, it almost certainly means the brief is contradicting the paper in ways the agent trusts. The fix is either better evidence grounding or better humility in the brief (more "this is an assumption" framing). It is not a fatal flaw; it's the design lesson the eval bought you.
