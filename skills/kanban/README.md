# Reusable Kanban Operator Skills

This skill family separates universal Kanban operator procedures from project adapters. Universal skills define invariant gates and forbidden actions. Project adapters provide repo paths, hosts, workers, verification commands, close-gate policy, examples, and known failure modes.

Prism-full is mandatory for Stage 2 planning/review/close-gate workflows where adapters require it.

## Universal skills bootstrapped
- kanban-card-spec
- kanban-review
- kanban-close-gate
- kanban-watch

## Project adapters
Adapters live under `skills/project-adapters/<project_id>/` and are loaded by deterministic scripts via JSON paths.

## Issue #51 Review Dispatch Lessons
- Parent orchestration cards are dependencies: after successful decomposition, mark the parent `done` to mean orchestration setup is complete. This does **not** mean the GitHub issue is complete.
- `ready` status enters implementation dispatch. Formal review must use `review` status so the review/`claim_review_task` path handles the card.
- `minimax-implementer` is review-only for Agent Garden unless an adapter explicitly overrides it; do not route it through implementation dispatch.
- Official Hermes/Kanban CLI transitions are the normal path. Direct SQLite writes are forbidden except explicitly authorized rescue operations with artifact evidence.
- Dispatcher-required skills must be available before spawn; hardcoded skill requirements such as the Issue #51 `sdlc-review` incident must be guarded or policy-documented.
