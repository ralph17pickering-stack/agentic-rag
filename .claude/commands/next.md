---
description: Plan and build the first item marked [ ] in PROGRESS.md (scan top to bottom, pick the earliest unchecked line)
---

# Next

Pick the **first** incomplete task from PROGRESS.md (top-to-bottom scan, earliest `[ ]` line), plan it interactively, then build it.

## Process

### 1. Read progress

Read `PROGRESS.md` in full. Scan from the **top of the file downward** and stop at the very first line marked `[ ]` (not started). Ignore completed `[x]` and in-progress `[-]` items entirely — do not consider which items appear "after" the last completed block. If everything is done, report that and stop.

### 2. Clarify ambiguities

Before planning, ask the user any questions needed to resolve ambiguities about scope, approach, or constraints. Keep questions focused — only ask what is genuinely unclear.

### 3. Write the plan

Save a detailed plan to `.agent/plans/` following the naming convention `{sequence}.{plan-name}.md`. The plan must:
- Open with a complexity indicator (✅ Simple / ⚠️ Medium / 🔴 Complex)
- List every task in execution order with clear acceptance criteria
- Include at least one validation step per task
- Note any dependencies or gotchas

For 🔴 Complex items, break the work into sub-plans before proceeding.

### 4. Compact context and build

After the plan file is saved, run `/compact` to clear the context window, then execute `/build .agent/plans/<plan-file>` to implement the feature.
