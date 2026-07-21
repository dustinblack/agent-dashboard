# Global Agent Instructions

## Task Delegation

When a `task` tool is available, use it proactively to
delegate work to specialist sub-agents:

- **explore** — use when you need to map unfamiliar
  parts of the codebase, find symbols across modules,
  or gather `path:line` evidence before making changes.
- **scout** — use when the answer requires official
  documentation, web research, API behavior, or
  knowledge not found in the repository.
- **general** — use for parallel units of work,
  multi-step implementation tasks, or research that
  may require edits to validate.
- **reviewer** — use after non-trivial edits to get an
  independent code review before presenting results.

Delegate when:
- The task involves multiple independent subtasks that
  can run in parallel.
- You need to research while simultaneously editing.
- The work benefits from isolated context (e.g.,
  exploring a subdirectory while the parent works on
  another).
- A code review would add confidence before committing.

Do NOT delegate trivial tasks (1–3 tool calls, 1–2
files) — handle those directly.
