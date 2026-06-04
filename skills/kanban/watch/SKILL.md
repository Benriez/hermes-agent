---
name: kanban-watch
description: "Use this skill when watching Hermes Kanban runs, detecting stale/ghost runs, classifying implementation completion, checking evidence readiness, or deciding whether a card is ready for review."
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
Read-only health watcher for active or recently completed Kanban workflows. Detects routing/workspace/provider hazards and emits structured diagnostics. Does not dispatch workers or mutate cards.

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
2. Inspect card status, assignee, workspace, pid, heartbeat, and logs.
3. Detect dead pid, stale heartbeat, wrong workspace, wrong assignee, forbidden provider mentions.
4. Detect if review completed with `review_passed: true` in run metadata (may not produce separate artifact files).
5. If scratch workspace is inaccessible but global artifacts + run metadata confirm completion, record as warning.
6. Run `scripts/check_run_health.py`.
7. Hand off to `kanban-recovery` if health fails.

## Allowed Actions
- Read local files, process state, adapter, card/run JSON.
- Write health JSON only when output path is provided.

## Forbidden Actions
- Do not assign anything to `superhermes`; it is Prism/context metadata only.
- Do not use `local-implementer` or `local-reviewer`.
- Do not direct-write SQLite.
- Do not create/delete Kanban cards unless operator requested and this skill explicitly says so.
- Do not close/reopen GitHub issues.
- Do not restart llama-swap or use local/qwopus fallback providers.

## Deterministic Scripts
- `scripts/check_run_health.py`

## Progressive Disclosure
- **Gotchas:** `../shared/gotchas.md` — ghost/stale runs, scratch workspace lifecycle, review metadata detection
- **Policy:** `../shared/universal-stage2-policy.json`
- **Full index:** `../shared/index.md`

## Failure Modes
- Worker spawned in source repo path instead of scratch.
- Review assigned to implementation worker (wrong dispatch path).
- Local/qwopus provider mention in logs.
- Ghost run: worker dead but DB shows `running` + PID stale.

## Next Skill Handoff
- Healthy: continue watching or proceed to review/close-gate.
- Unhealthy: `kanban-recovery`.
