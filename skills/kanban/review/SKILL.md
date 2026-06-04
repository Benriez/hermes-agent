---
name: kanban-review
description: "Use this skill when moving cards into formal review, validating minimax review eligibility, auditing REVIEW_PASS/FAIL evidence, or preventing ready+minimax dispatch mistakes."
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
- Review artifact JSON path (may be null if alternative evidence is available).
- Review report TXT path (may be null if alternative evidence is available).
- Output log path (may be null if alternative evidence is available).
- Reviewer identity and changed-files list when available.
- If separate review artifact paths are null, use kanban run metadata to confirm review outcome.

## Steps
1. Confirm reviewer matches adapter review worker unless policy override exists.
2. Check for explicit review evidence: separate review JSON/TXT files, OR kanban run metadata with `review_passed: true`, OR explicit `REVIEW_PASS` in run summary.
3. Require browser evidence when UI files changed or adapter requires browser verification.
4. Run `scripts/check_review_evidence.py`.
5. Hand off pass to `kanban-close-gate`; fail to rework/recovery.

## Accepted Review Evidence

**Preferred:** Explicit review artifact JSON + review report TXT + output log.

**Acceptable alternative:** Kanban run metadata with:
- `review_passed: true`
- `REVIEW_PASS` in the `summary` field
- `changed_files` list matching the implementation

Missing separate review artifact files is a **warning**, not automatic failure, when run metadata provides strong explicit evidence.

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
- Review artifact JSON (preferred; null acceptable with strong run metadata).
- Review report TXT (preferred; null acceptable with strong run metadata).
- Output log (preferred; null acceptable with strong run metadata).
- Structured review-evidence check JSON.

## Deterministic Scripts
- `scripts/check_review_evidence.py`

## Progressive Disclosure
- **Gotchas:** `../shared/gotchas.md` — sdlc-review availability guard, review metadata evidence, dispatch semantics
- **Policy:** `../shared/universal-stage2-policy.json`
- **Full index:** `../shared/index.md`

## Next Skill Handoff
- REVIEW_PASS: `kanban-close-gate`.
- REVIEW_FAIL: create/reuse rework workflow only when operator/board policy permits.

## Failure Modes
- Missing explicit outcome.
- Review worker is implementation worker.
- UI diff without browser evidence.

## Review Status Dispatch Semantics
- Cards requiring formal review must transition to status `review`; do not leave a review-assignee card in `ready`.
- `ready` uses the implementation dispatch path. `review` uses the formal review path / `claim_review_task`.
- `minimax-implementer` is review-only unless a project adapter explicitly allows otherwise; do not route it through implementation dispatch.
- Review output must contain an explicit `REVIEW_PASS` or `REVIEW_FAIL` plus review artifact JSON, report TXT, and output log.
- Before starting review, verify dispatcher-required skills are available. The Issue #51 run 88 crash (`Unknown skill(s): sdlc-review`) is a known failure mode when review dispatch hardcodes an unavailable skill.
- `sdlc-review` is an optional review skill; it must be availability-guarded before being passed as a required skill to the worker. The `_resolve_task_skill_in_home()` pattern in `_default_spawn` handles this correctly.
