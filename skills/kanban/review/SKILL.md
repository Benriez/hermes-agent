---
name: kanban-review
description: "Use when reviewing Kanban implementation output. Requires auditable artifact JSON, report TXT, output log, explicit REVIEW_PASS or REVIEW_FAIL, and adapter review-worker policy."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [kanban, operator, workflows, prism-full]
    related_skills: [prism-full]
---

# Kanban Review

## Overview
Performs or validates review evidence for a completed implementation card. Reviews must be auditable and adapter-driven. Use `prism-full` for Stage 2 review reasoning when adapter policy requires it.

## When to Use
- After implementation worker reports completion.
- Before marking review pass/fail.
- Before parent auto-done or close-gate checks.

## Required Inputs
- Adapter JSON.
- Review artifact JSON path.
- Review report TXT path.
- Output log path.
- Reviewer identity and changed-files list when available.

## Steps
1. Confirm reviewer matches adapter review worker unless policy override exists.
2. Confirm artifact/report/log exist.
3. Confirm explicit `REVIEW_PASS` or `REVIEW_FAIL`.
4. Require browser evidence when UI files changed or adapter requires browser verification.
5. Run `scripts/check_review_evidence.py`.
6. Hand off pass to `kanban-close-gate`; fail to rework/recovery.

## Allowed Actions
- Read logs, artifacts, reports, adapter.
- Write review validation artifact if output path is provided.

## Forbidden Actions
- Do not assign anything to `superhermes`; it is Prism/context metadata only.
- Do not use `local-implementer` or `local-reviewer`.
- Do not direct-write SQLite.
- Do not create/delete Kanban cards unless this skill explicitly says so and the operator requested it.
- Do not close/reopen GitHub issues.
- Do not restart llama-swap or use local/qwopus fallback providers.

## Required Artifacts
- Review artifact JSON.
- Review report TXT.
- Output log.
- Structured review-evidence check JSON.

## Deterministic Scripts
- `scripts/check_review_evidence.py`

## Next Skill Handoff
- REVIEW_PASS: `kanban-close-gate`.
- REVIEW_FAIL: create/reuse rework workflow only when operator/board policy permits.

## Failure Modes
- Missing explicit outcome.
- Review worker is implementation worker.
- UI diff without browser evidence.

