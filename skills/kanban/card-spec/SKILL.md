---
name: kanban-card-spec
description: "Use when creating, validating, decomposing, or repairing Hermes Kanban parent/child cards — especially Agent Garden intake, implementation, review, and close-gate workflow cards. Ensures prism-full, host, workspace, worker, and metadata gates are correct."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [kanban, operator, workflows, prism-full]
    related_skills: [prism-full]
---

# Kanban Card Spec

## Overview
Creates or validates safe Kanban card specifications from operator/project intent. This skill is universal: load project facts from an adapter JSON, never hardcode Agent Garden or Mac paths. Use prism-full for architecture-sensitive Stage 2 cards when the adapter requires it.

## When to Use
- Before creating or re-specifying parent/child cards.
- Before approving a worker dispatch.
- When checking that source-host paths are metadata only.

## Required Inputs
- Project adapter path or resolved adapter object.
- Intended parent/child card metadata.
- Board name, workers, required skills, prism context.

## Steps
1. Confirm adapter requires/declares `prism-full` if Stage 2 policy applies.
2. Verify parent workspace is orchestration-host scratch, not source repo.
3. Verify repo path is body/metadata only.
4. Verify implementation/review workers match adapter policy.
5. Run `scripts/validate_parent_card.py` against adapter and candidate card JSON.
6. Hand off valid cards to `kanban-decompose` or `kanban-implementation`.

## Allowed Actions
- Read adapters, policy files, card JSON, and safe Kanban CLI output.
- Write validation artifacts when requested.

## Forbidden Actions
- Do not assign anything to `superhermes`; it is Prism/context metadata only.
- Do not use `local-implementer` or `local-reviewer`.
- Do not direct-write SQLite.
- Do not create/delete Kanban cards unless this skill explicitly says so and the operator requested it.
- Do not close/reopen GitHub issues.
- Do not restart llama-swap or use local/qwopus fallback providers.

## Required Artifacts
- Parent-card validation JSON when gating dispatch.

## Deterministic Scripts
- `scripts/validate_parent_card.py`

## Progressive Disclosure
- **Gotchas:** `../shared/gotchas.md` — intake rules, runtime vs workflow skills, parent semantics
- **Incident examples:** `../shared/examples/intake-auto-dispatch-skill-resolution-learning.json`
- **Policy:** `../shared/universal-stage2-policy.json`
- **Full index:** `../shared/index.md`

## Next Skill Handoff
- Valid parent: `kanban-decompose` or implementation-specific card creation.
- Invalid parent: `kanban-recovery` or operator correction.

## Intake Parent Card Creation Rules

**Critical — intake parent cards must follow these rules:**

1. **Initial status**: Always use `--initial-status blocked`.
   Intake parent cards must **never** be created with default `ready` status.
   ```bash
   hermes kanban --board agent-garden create \
     --title "Stage 1 Intake — <issue>" \
     --initial-status blocked \
     --skills prism-full \
     ...
   ```

2. **Runtime skills field**: The `--skills` argument and card `skills` field
   are interpreted as **worker runtime skills** passed to the CLI as `--skills`.
   Only worker-loadable runtime skills belong here (e.g. `prism-full`).

3. **Workflow/operator skills belong in body metadata only**:
   - `workflow_skill: kanban-card-spec`
   - `operator_skills_used: [kanban-card-spec, kanban-watch]`
   - `required_skills: [prism-full]` (dispatcher routing hint)

4. **Forbidden in runtime skills for intake parents**:
   - `kanban-card-spec`
   - `kanban-watch`
   - `kanban-review`
   - `kanban-close-gate`

   These are operator/workflow skills. They exist at
   `skills/kanban/<skill>/SKILL.md` but are **not** in the worker skill
   search path (`~/.hermes/skills/` or `~/.hermes/custom-skills/`).
   Placing them in the card `skills` field causes worker startup failure:
   `Unknown skill(s): kanban-card-spec, kanban-watch`.

5. **Assignee**: Do not assign intake parent cards to spawnable workers
   unless intentionally dispatchable. Use blocked status as the primary
   non-dispatchable guard.

## Failure Modes
- Parent spawned in `/Users/...` or Windows repo path.
- Missing `prism-full`.
- `superhermes` appears as assignee.
- Intake parent created with default `ready` status → auto-dispatched.
- Workflow skills (`kanban-card-spec`, `kanban-watch`) placed in card
  `skills` field → worker crashes with `Unknown skill(s)`.


## Parent Dependency Semantics
- Hermes treats parent cards as dependencies for child execution.
- After successful intake/decomposition, complete the orchestration parent (`done`) before child dispatch/promotion.
- Parent `done` means orchestration setup is complete; it does **not** mean the GitHub issue is complete, reviewed, or close-gate approved.
- Child execution/review/close-gate evidence remains required before any issue close action.
