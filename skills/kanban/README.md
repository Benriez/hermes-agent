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
