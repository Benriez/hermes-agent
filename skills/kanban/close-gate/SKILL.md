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

## Required Inputs
- Adapter JSON.
- Issue number (may be null for internal follow-up cards).
- Parent card summary JSON.
- Children summary JSON.
- Review evidence (see accepted sources below).
- Commit hash and remote/branch.
- Test/browser evidence paths or status.

## Accepted Review Evidence Sources

Close-gate accepts ANY of the following as sufficient REVIEW_PASS evidence:

1. **Separate review artifact JSON + review report TXT + output log** (preferred)
2. **Kanban run metadata** with `review_passed: true` AND `agent log` (structured watch artifact acceptable)
3. **Kanban run metadata** with `review_passed: true` AND explicit `REVIEW_PASS` in run summary

Missing separate review JSON/TXT files are a **warning, not a failure**, if alternative evidence proves REVIEW_PASS.

## Required Artifacts
- Close-gate JSON with `passed`, `missing_gates`, and `warnings` (if any).
- Close-comment evidence draft.
- Close-gate must document which review evidence source was used.

## Deterministic Scripts
- `scripts/check_close_gate.py`

## GitHub Close Not Applicable Cases

- `github.issue_number` is `null` → GitHub close is **not applicable**. Record `github_close_not_applicable_without_explicit_issue`. This is not a failure.
- Internal follow-up cards without GitHub issue targets are common; close-gate must pass for these.

## Remote Verification

Close-gate must verify commit exists on the **actual remote/branch** used in the task, not assume a pre-described remote. Use `git ls-remote <remote> refs/heads/<branch>` to confirm.

## Next Skill Handoff
- Passed: operator close/comment flow (if GitHub issue exists and operator approves).
- Passed: task complete (if GitHub issue is null/inapplicable).
- Failed: `kanban-recovery` or targeted rework.

## Failure Modes
- Commit not pushed.
- Parent/child incomplete.
- REVIEW_PASS missing and no acceptable alternative evidence.
- Remote verification fails (commit not on stated remote/branch).

## Warnings That Are Not Failures

The following are **warnings** that do not prevent a CLOSE_GATE_PASS:

1. Scratch workspace was cleaned (task lifecycle cleanup; use global artifacts + run metadata)
2. No separate review JSON/TXT (use run metadata + agent log)
3. GitHub issue number is null (internal follow-up card; GitHub close not applicable)
4. Unrelated dirty files in working tree (verify only intended files were committed)
5. Remote is benriez/bodi instead of assumed origin/bodi (verify against actual target)

Close-gate classification:
- `CLOSE_GATE_PASS` — all core gates pass, no warnings
- `CLOSE_GATE_PASS_WITH_WARNINGS` — all core gates pass, non-critical warnings exist

## Review-Pass and Issue-Close Separation
## Review-Pass and Issue-Close Separation
- Close-gate can pass only after explicit `REVIEW_PASS` evidence and required artifact/report/log checks.
- Close-gate passing does not automatically close a GitHub issue.
- If the operator forbids issue close, report close-gate `PASSED` while leaving the GitHub issue open.
- GitHub issue close is a separate operator-approved action after close-gate evidence is produced.
