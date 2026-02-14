---
description: Plan and build the next unchecked item from PROGRESS.md
---

# Next

Pick the next unchecked task from PROGRESS.md, plan it interactively, then build it.

## Process

### 1. Read progress

Read `PROGRESS.md` in full. Find the first item marked `[ ]` (not started). If everything is done, report that and stop.

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
