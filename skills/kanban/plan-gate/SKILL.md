---
name: kanban-plan-gate
description: "Use this skill before dispatching implementation work when a Kanban card needs a validated plan, explicit success criteria, bounded scope, forbidden actions, and a verification strategy."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [kanban, operator, planning, gate, prism-full]
    related_skills: [prism-full]
---

# Kanban Plan Gate

## Overview
Validates that a Kanban task has a reviewable implementation plan before dispatch. The goal is to prevent workers from solving the wrong problem correctly. This skill is universal: it uses worker roles and adapter context, never concrete project worker names or local project paths.

## When to Use
- Before dispatching implementation work with ambiguous scope, risk, or multiple possible solution paths.
- Before approving a task that needs explicit success criteria, non-goals, forbidden actions, or verification evidence.
- When converting operator intent into implementation-ready work.

## When Not to Use
- For pure read-only audits that will not dispatch implementation.
- For already-completed work that is entering review or close-gate.
- For trivial operator-approved mechanical edits where scope and verification are already explicit in the task body.

## Required Plan Fields
A valid `plan_gate` must include:
- `problem_statement`
- `operator_intent`
- non-empty `success_criteria`
- explicit `non_goals`
- explicit `forbidden_actions`
- `scope.allowed_paths`, `scope.forbidden_paths`, and `scope.affected_systems`
- `adapter_context` for project-specific facts, if any
- non-empty `execution_plan`
- `verification_strategy.commands`, `manual_checks`, and `evidence_expected`
- `risk_assessment.risk_level`, `known_risks`, and `rollback_or_recovery`
- `dispatch_decision.ready_for_implementation`, `required_worker_role`, `requires_operator_approval`, and `reason`

## Pass Criteria
- The real problem and operator intent are clear.
- Success criteria are non-empty and checkable.
- Non-goals and forbidden actions are explicit.
- Scope and affected systems are bounded.
- Verification strategy is defined before implementation.
- Dispatch decision is explicit.
- Required worker is a role (for example `implementation_worker`), not a concrete adapter worker name.

## Fail Criteria
- Missing or empty success criteria.
- Missing forbidden actions.
- Missing verification strategy or expected evidence.
- Dispatch decision is absent or ambiguous.
- Universal plan requires concrete worker names instead of adapter-declared roles.
- Adapter-specific assumptions are mixed into universal rules instead of `adapter_context`.

## Relationship to Other Kanban Skills
- **card-spec:** validates card structure and runtime/workflow skill separation.
- **plan-gate:** validates that the intended implementation is the right bounded plan before dispatch.
- **watch:** monitors an active run after dispatch.
- **review:** verifies implementation evidence and REVIEW_PASS/FAIL after worker completion.
- **close-gate:** decides whether completed/reviewed work can be closed or released.

## Deterministic Script
- `scripts/check_plan_gate.py <plan.json>`

## Progressive Disclosure
- **Full index:** `../shared/index.md`
- **Gotchas:** `../shared/gotchas.md`
- **Policy:** `../shared/universal-stage2-policy.json`
- **Checker:** `scripts/check_plan_gate.py`
- **Examples:** `examples/`

## Forbidden Actions
- Do not modify Kanban cards unless the operator explicitly asks for card changes.
- Do not dispatch workers from this skill by itself.
- Do not direct-write SQLite.
- Do not encode adapter concrete worker names into universal policy or examples.
- Do not close/reopen GitHub issues.

## Next Skill Handoff
- PASS: implementation dispatch may proceed if the operator/workflow allows it.
- FAIL: revise the card/plan before dispatch.
