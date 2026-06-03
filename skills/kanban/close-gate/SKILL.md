---
name: kanban-close-gate
description: "Use before closing a GitHub issue from Kanban. Verifies parent/children done, review pass evidence, tests/browser gates, commit exists and is pushed."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [kanban, operator, workflows, prism-full]
    related_skills: [prism-full]
---

# Kanban Close Gate

## Overview
Final read-only gate before any issue close action. This skill does not close issues by itself; it determines whether close is safe and what evidence must be included. Use `prism-full` for Stage 2 close decisions where adapter policy requires it.

## When to Use
- Before closing or commenting on a GitHub issue.
- After REVIEW_PASS and parent auto-done.
- When verifying commit/push/test/browser evidence.

## Required Inputs
- Adapter JSON.
- Issue number.
- Parent card summary JSON.
- Children summary JSON.
- Review artifact/report/log paths.
- Commit hash and branch.
- Test/browser evidence paths or status.

## Steps
1. Verify issue exists if issue metadata was provided.
2. Verify parent and all children are done.
3. Verify no open rework cards.
4. Verify review pass artifact exists.
5. Verify tests/build/browser gates are pass or explicitly not applicable.
6. Verify commit exists and remote branch contains commit.
7. Run `scripts/check_close_gate.py`.
8. Produce close-comment evidence; only operator-approved tooling may close.

## Allowed Actions
- Read git state, adapter, artifacts, Kanban summaries.
- Network checks only if explicitly requested for remote commit/issue existence.

## Forbidden Actions
- Do not assign anything to `superhermes`; it is Prism/context metadata only.
- Do not use `local-implementer` or `local-reviewer`.
- Do not direct-write SQLite.
- Do not create/delete Kanban cards unless this skill explicitly says so and the operator requested it.
- Do not close/reopen GitHub issues.
- Do not restart llama-swap or use local/qwopus fallback providers.

## Required Artifacts
- Close-gate JSON with `passed` and `missing_gates`.
- Close-comment evidence draft.

## Deterministic Scripts
- `scripts/check_close_gate.py`

## Next Skill Handoff
- Passed: operator close/comment flow.
- Failed: `kanban-recovery` or targeted rework.

## Failure Modes
- Commit not pushed.
- Parent/child incomplete.
- REVIEW_PASS missing.

