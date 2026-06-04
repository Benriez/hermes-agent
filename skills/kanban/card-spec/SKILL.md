---
name: kanban-card-spec
description: "Use when specifying or validating Kanban parent/child cards before dispatch. Ensures prism-full, host, workspace, worker, and metadata gates are correct."
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

## Next Skill Handoff
- Valid parent: `kanban-decompose` or implementation-specific card creation.
- Invalid parent: `kanban-recovery` or operator correction.

## Failure Modes
- Parent spawned in `/Users/...` or Windows repo path.
- Missing `prism-full`.
- `superhermes` appears as assignee.


## Parent Dependency Semantics
- Hermes treats parent cards as dependencies for child execution.
- After successful intake/decomposition, complete the orchestration parent (`done`) before child dispatch/promotion.
- Parent `done` means orchestration setup is complete; it does **not** mean the GitHub issue is complete, reviewed, or close-gate approved.
- Child execution/review/close-gate evidence remains required before any issue close action.
