# Shared Kanban Operator Failure Modes

- Parent card spawned with source-host repo path instead of Pi scratch workspace.
- Project path stored as workspace rather than metadata.
- `superhermes` used as assignee instead of Prism/context metadata.
- Review routed to implementation worker.
- GitHub issue closed before commit and push are verified.
- Review evidence is textual only, missing artifact/report/output log.
- UI files changed without browser evidence when adapter requires browser verification.
- Windows-only commands accidentally run on Mac or Pi.

## Issue #51 review-dispatch failures
- Parent orchestration card left `blocked`/`todo` after decomposition blocks child dispatch because Hermes treats parents as dependencies.
- Review card assigned to `minimax-implementer` but left in `ready` status is routed through implementation dispatch and skipped/blocked.
- `minimax-implementer` is correctly blocked from implementation dispatch; formal review requires `review` status.
- Review dispatch hardcoded `sdlc-review` without an availability guard; run 88 crashed with `Unknown skill(s): sdlc-review`.
- Direct SQLite status transition `ready -> review` was a rescue operation and must not become normal workflow. Add/request an official CLI transition instead.
