---
description: End-of-session wrap-up — update docs, save plans, and commit
---

# Wind Down

Wrap up the current session by updating project documentation and committing.

## Steps

1. **Review what changed this session** — Run `git diff` and `git status` to understand all modifications made.

2. **Update LESSONS.md** — Add a new session section with any lessons learned, gotchas encountered, or patterns discovered during this session. Follow the existing format (session header, subheadings per lesson, bold key takeaway + explanation). Skip if nothing notable was learned.

3. **Update PROGRESS.md** — Mark completed tasks with `[x]`, in-progress with `[-]`, and add any new line items for work done. Ensure the module status accurately reflects the current state.

4. **Save design decisions** — If any plans were discussed or executed this session that don't already have a file in `.agent/plans/`, create one following the naming convention `{sequence}.{plan-name}.md`. Mark completed plans with **Status: Completed** at the top.

5. **Commit to git** — Stage all changes and create a commit with a clear message summarising the session's work. Do NOT push unless explicitly asked.
