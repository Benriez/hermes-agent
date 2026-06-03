---
name: kanban-watch
description: "Use when monitoring Kanban cards/runs for stale heartbeat, dead pid, wrong workspace, wrong assignee, or forbidden provider/worker mentions."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [kanban, operator, workflows, prism-full]
    related_skills: [prism-full]
---

# Kanban Watch

## Overview
Read-only health watcher for active or recently completed Kanban workflows. It detects routing/workspace/provider hazards and emits structured diagnostics. It does not dispatch workers or mutate cards.

## When to Use
- During long-running worker execution.
- After failed spawn or stale run.
- Before deciding whether recovery is needed.

## Required Inputs
- Adapter JSON.
- Card/run/event JSON exported by safe Hermes/Kanban CLI or logs.
- Optional stale heartbeat threshold.

## Steps
1. Load adapter and expected workers/hosts.
2. Inspect card status, assignee, workspace, pid, heartbeat, and logs if provided.
3. Detect dead pid, stale heartbeat, wrong workspace, wrong assignee, forbidden provider mentions.
4. Run `scripts/check_run_health.py`.
5. Hand off to `kanban-recovery` if health fails.

## Allowed Actions
- Read local files and process state.
- Write health JSON only when output path is provided.

## Forbidden Actions
- Do not assign anything to `superhermes`; it is Prism/context metadata only.
- Do not use `local-implementer` or `local-reviewer`.
- Do not direct-write SQLite.
- Do not create/delete Kanban cards unless this skill explicitly says so and the operator requested it.
- Do not close/reopen GitHub issues.
- Do not restart llama-swap or use local/qwopus fallback providers.

## Required Artifacts
- Run-health JSON when monitoring evidence is needed.

## Deterministic Scripts
- `scripts/check_run_health.py`

## Next Skill Handoff
- Healthy: continue watching or proceed to review/close gate.
- Unhealthy: `kanban-recovery`.

## Failure Modes
- Worker spawned in source repo path.
- Review assigned to implementation worker.
- Local/qwopus provider mention in logs.

