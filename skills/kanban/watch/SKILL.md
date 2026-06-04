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
4. Detect if review has completed with explicit REVIEW_PASS in run metadata (review may not produce separate artifact files — check `kanban runs --json` for `review_passed: true`).
5. If scratch workspace is inaccessible but global artifacts and run metadata confirm workflow completion, record as warning rather than failure.
6. Run `scripts/check_run_health.py`.
7. Hand off to `kanban-recovery` if health fails.

## Scratch Workspace Lifecycle Warning

Scratch workspaces (`workspaces/<card-id>/`) may be cleaned by the workspace lifecycle after task completion. Implementation artifacts stored only in scratch workspace become inaccessible.

**Rule:** Do not treat inaccessible scratch workspace as a health failure if global evidence exists:
- Commit hash on remote
- Global artifacts (`~/.hermes/artifacts/`)
- Kanban run metadata with explicit `review_passed: true`
- Agent log confirming review completion

**Watch task should record `scratch_workspace_cleaned: true` as a warning, not a health failure.**

## Review Evidence Detection

Watch tasks may encounter review runs where:
- Separate `review-report.json` / `review-report.txt` are absent
- `kanban runs --json` shows `review_passed: true` in metadata
- Agent log shows explicit `REVIEW_PASS` or `REVIEW_FAIL`

**Rule:** Accept run metadata + agent log as sufficient review evidence. Record `review_evidence_source: "run_metadata + agent_log"` in watch artifact.

## Required Artifacts
- Run-health JSON when monitoring evidence is needed.
- Watch artifact JSON capturing all detected states and warnings.
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


## Issue #51 Watch Warnings
- Flag `status=ready` + `assignee=minimax-implementer` as a policy warning: ready uses implementation dispatch, while minimax review requires `review` status.
- Flag review-run crashes containing `Unknown skill(s): sdlc-review` as dispatcher skill-availability gaps.
- Flag direct SQLite status edits as rescue-only violations unless the operator explicitly authorized a rescue and an artifact records it.
- Watchers must remain read-only: diagnose, write artifacts/reports, and recommend an official CLI transition or policy fix.

## Issue t_50dd31da Watch Warnings — Intake Parent Auto-Dispatch

The following patterns are **policy violations** for Stage 1 intake parent cards:

1. **status=ready on intake parent card**:
   - Intake parent cards must be created with `--initial-status blocked`.
   - A `ready` intake parent means the dispatcher will attempt to auto-assign
     and spawn a worker. This must not happen for orchestration-only parents.
   - Recommended action: block immediately, investigate how `ready` was created,
     update intake procedure to always use `--initial-status blocked`.

2. **spawnable assignee on intake parent card**:
   - Intake parent cards must not be assigned to spawnable workers.
   - `deep-implementer` (or any spawnable profile) as assignee on an intake
     parent is a warning sign. If the parent is `ready`, the dispatcher will
     spawn the worker immediately.
   - Recommended action: reclaim, block, verify no child cards exist.

3. **card `skills` field includes `kanban-card-spec` or `kanban-watch`**:
   - These are operator/workflow skills, not worker runtime skills.
   - The card `skills` field is passed to workers as `--skills` at startup.
   - Worker skill resolver searches `~/.hermes/skills/` and
     `~/.hermes/custom-skills/` only. `kanban-card-spec` and `kanban-watch`
     live under `hermes-agent/skills/kanban/` which is NOT in the search path.
   - Result: worker crashes at startup with
     `Unknown skill(s): kanban-card-spec, kanban-watch`.
   - Recommended action: move these skill names from card `skills` field to
     body metadata (`workflow_skill:`, `operator_skills_used:`).

4. **Card body should contain workflow metadata**:
   - Correct metadata fields in card body:
     ```
     workflow_skill: kanban-card-spec
     operator_skills_used: [kanban-card-spec, kanban-watch]
     required_skills: [prism-full]
     ```
   - Correct card `--skills` argument:
     ```
     --skills prism-full
     ```
   - Wrong (causes worker crash): `--skills kanban-card-spec,kanban-watch,prism-full`

5. **Known incident**: t_50dd31da run 90 auto-dispatched despite being an
   intake parent. Root causes:
   - Card created with default `ready` status (no `--initial-status blocked`).
   - `deep-implementer` auto-assigned by dispatcher via `default_assignee`.
   - `kanban-card-spec` and `kanban-watch` in card `skills` field caused
     worker startup crash `Unknown skill(s): kanban-card-spec, kanban-watch`.
   - Mitigation: manual reclaim + block.
