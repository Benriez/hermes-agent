# Shared Kanban Operator Failure Modes

- Parent card spawned with source-host repo path instead of Pi scratch workspace.
- Project path stored as workspace rather than metadata.
- `superhermes` used as assignee instead of Prism/context metadata.
- Review routed to implementation worker.
- GitHub issue closed before commit and push are verified.
- Review evidence is textual only, missing artifact/report/output log.
- UI files changed without browser evidence when adapter requires browser verification.
- Windows-only commands accidentally run on Mac or Pi.
