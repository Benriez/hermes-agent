---
name: kanban-partition-check
description: "Use this skill before dispatching or running concurrent Kanban implementation work when tasks may touch overlapping files, systems, adapters, repositories, databases, services, or operational state."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [kanban, operator, concurrency, partition, prism-full]
    related_skills: [prism-full]
---

# Kanban Partition Check

## Overview
Validates whether candidate work can safely run concurrently with active or planned work. The goal is to prevent parallel workers from producing conflicting diffs, invalid evidence, overlapping service changes, or unsafe operational state changes. This skill is universal: it uses worker roles, paths, systems, locks, and adapter context; concrete worker names and project facts belong to adapters.

## When to Use
- Before dispatching concurrent implementation work.
- Before approving a task that writes files, changes service state, touches databases, modifies shared config, or affects operational state while other work is active.
- When splitting one project into parallel child cards.
- When an active run and a candidate run may touch the same repository, adapter, paths, services, locks, or evidence artifacts.

## When Not to Use
- For a single serialized task with no concurrent implementation work.
- For pure read-only audits with no write scope and no shared lock use.
- For review or close-gate only, unless the review/close-gate writes files, service state, or issue state.

## Required Partition Fields
A valid `partition_check` must include:
- candidate task identity and adapter context
- candidate worker role and operation type
- allowed, forbidden, read-only, and write paths
- affected systems
- exclusive locks and shared read locks
- active/planned work with the same scope fields
- explicit conflict rules
- explicit concurrency decision

## Conflict Types
- **write/write path overlap:** blocks by default.
- **exclusive lock overlap:** blocks by default.
- **write/read path overlap:** warns by default; strict mode may block.
- **same repository with unspecified write scope:** warns or blocks depending on unknown-scope policy.
- **unknown candidate write scope:** blocks or requires operator approval.
- **adapter/project scope ambiguity:** requires operator review when it could hide overlap.

## Pass Criteria
- Candidate write paths are explicit.
- No write/write overlap with active work.
- No exclusive lock conflict.
- Same-repo active work has disjoint write scope or explicit operator approval.
- Decision explicitly says whether concurrency is allowed, serialization is required, and operator approval is required.

## Warn Criteria
- Candidate writes a path another task reads.
- Same repository has incomplete but not blocking scope.
- Shared read locks overlap without writes.

## Fail/Block Criteria
- Candidate or active work has unknown write scope and policy blocks unknown scope.
- Write/write path overlap exists.
- Exclusive lock conflict exists.
- Decision claims concurrency is allowed despite blocking conflicts.

## Relationship to Other Kanban Skills
- **card-spec:** validates card structure and runtime/workflow skill separation.
- **plan-gate:** validates that each task has the right bounded plan.
- **partition-check:** validates that multiple bounded plans can run concurrently.
- **watch:** monitors active runs after dispatch.
- **review:** verifies completed implementation evidence.
- **close-gate:** decides close/release eligibility after review.

## Deterministic Script
- `scripts/check_partition.py <partition.json>`

## Progressive Disclosure
- **Full index:** `../shared/index.md`
- **Gotchas:** `../shared/gotchas.md`
- **Policy:** `../shared/universal-stage2-policy.json`
- **Checker:** `scripts/check_partition.py`
- **Examples:** `examples/`

## Forbidden Actions
- Do not modify Kanban cards unless the operator explicitly asks for card changes.
- Do not dispatch workers from this skill by itself.
- Do not direct-write SQLite.
- Do not encode adapter concrete worker names into universal policy or examples.
- Do not close/reopen GitHub issues.

## Next Skill Handoff
- PASS/WARN: implementation dispatch may proceed only if the workflow/operator accepts warnings.
- BLOCK: serialize work, narrow scope, or request operator approval before dispatch.
