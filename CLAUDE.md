# Working order

Standing preferences for how Claude works with this user. Applies across tasks.

## Orchestration (execution style)
- **Claude leads.** Claude holds the plan, reads the code, makes the
  design/architecture calls, and writes **targeted dispatches** — a precise spec
  per unit of work: files to touch, interfaces, constraints, done-conditions, and
  what *not* to touch.
- **Subagents write the code**, following those dispatches.
  - Default subagent model: **`sonnet`**.
  - Use **`haiku`** for mechanical / low-ambiguity work — scaffolding, repetitive
    edits, applying a stated pattern across many files.
  - Reserve **`opus`** / Claude itself for open design questions. Resolve those
    **before** dispatching; never hand an undecided design to a subagent.
- **Claude verifies and integrates** every result. Run the tests/checks, reconcile
  parallel agents, own the final state. A subagent's report is never shipped unread.
- Spawn agents only when there is real work to hand off — not to look busy.

## Content calibration (this user)
- **Keep material at full rigor. Do not dumb it down**, and do not over-simplify to
  meet the reader.
- The user is actively learning specialized terminology (e.g. yeshivish / Torah
  terms). Help them **understand** terms — glossaries, plain-language glosses,
  pronunciations, inline definitions — added **alongside** advanced content, never
  by lowering the content itself.
- **Cite sources faithfully and neutrally.** Do not over-interpret or editorialize
  primary sources. Keep "what the source says" clearly distinct from interpretive or
  hashkafic framing.

## Notes
- This file is the durable copy (committed to the repo, which survives the ephemeral
  web container). A user-level `~/.claude/CLAUDE.md` mirror also exists but may not
  persist between web sessions.
