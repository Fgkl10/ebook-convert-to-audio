# Project rules

## Language
- Write everything in this repository in English: code, comments, docs, commit messages, PR text.
- Exception: translations are written in their language: `README.zh-CN.md`, `README.zh-TW.md`, `android/app/src/main/res/values-b+zh+*/` and `desktop/web/i18n/zh-*.json` (desktop D-041).

## Component documentation (required)
Every component (a top-level source folder such as `desktop/`, and later `android/`) keeps its own
docs in `<component>/docs/`. Never put component docs in the repository root.

Each `<component>/docs/` folder contains:

| File | Contents |
|---|---|
| `workflow.md` | Workflow diagrams (Mermaid): the main runtime flows, step by step |
| `architecture.md` | Architecture diagram (Mermaid) + module responsibilities, data formats, interfaces |
| `decisions.md` | Decision log: one entry per design decision with Context / Decision / Why / Consequences |
| `test-cases.md` | Written test-case library: ID, area, preconditions, steps, expected result, and whether it is automated (link the test) or manual |

Keep the docs in sync with the code:
- When you add a component, create its `docs/` folder with all four files.
- When a change alters a flow, a module boundary, a data format, or makes a design choice,
  update the matching doc in the same branch/PR.
- When you add or change behavior, add or update test cases in `test-cases.md`; mark each
  as automated (with the pytest/test name) or manual.
- Use Mermaid for diagrams so they render on GitHub.
- Mark known gaps honestly, such as behavior that is untested or a known limitation.

When to update the docs:
- Do not update docs after every change. Update docs only once, when a task is finished or
  after a major change, as the last step before the final commit.
- While working, keep notes in your head and batch all doc edits together at the end.
- If the conversation is close to its context limit, update the docs before it runs out.

## Editing files
- Always create and edit files with the Write/Edit tools. Never write file contents through
  shell heredocs or echo.

## Git workflow
- One branch + one PR per milestone, targeting `master`. Wait for the PR to merge before
  starting the next milestone.
