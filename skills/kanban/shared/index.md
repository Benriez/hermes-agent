# Kanban Skills — Progressive Disclosure Index

**Purpose:** Navigation entry point for Kanban operator skills. SKILL.md files are focused triggers. This index points to deeper context.

---

## Skill Trigger Guide

| When you need to... | Use this skill | Key SKILL.md |
|---|---|---|
| Create or validate a parent/child card | `kanban-card-spec` | `skills/kanban/card-spec/SKILL.md` |
| Validate a plan before implementation dispatch | `kanban-plan-gate` | `skills/kanban/plan-gate/SKILL.md` |
| Validate partition safety before parallel dispatch | `kanban-partition-check` | `skills/kanban/partition-check/SKILL.md` |
| Watch a running card, detect ghost runs | `kanban-watch` | `skills/kanban/watch/SKILL.md` |
| Validate review evidence, audit REVIEW_PASS | `kanban-review` | `skills/kanban/review/SKILL.md` |
| Run close-gate, classify pass/fail/warnings | `kanban-close-gate` | `skills/kanban/close-gate/SKILL.md` |
| Validate commit scope, safe staging, and push before close-gate | `kanban-gitter` | `skills/kanban/gitter/SKILL.md` |

---

## Deeper Context Files

### Gotchas (First-Class Incident Memory)
→ `skills/kanban/shared/gotchas.md`

All known failure modes, edge cases, and non-obvious behaviors. Start here when something behaves unexpectedly.

### Failure Modes (Additional Context)
→ `skills/kanban/shared/failure-modes.md`

Structural failure mode descriptions beyond individual gotchas.

### Universal Stage 2 Policy
→ `skills/kanban/shared/universal-stage2-policy.json`

Policy flags, gates, and enforcement rules for Stage 2 workflows.

### Examples (Incident Memory)
→ `skills/kanban/shared/examples/`

JSON incident records. Each example documents a completed workflow with decisions and warnings.

Key examples:
- `sdlc-review-availability-guard-close-gate-learning.json`
- `intake-auto-dispatch-skill-resolution-learning.json`
- `issue-51-review-dispatch-learning.json`
- `issue-48-success.json`

### Project-Specific Examples
→ `skills/project-adapters/agent-garden/examples/`

Same structure as shared examples, but Agent Garden specific.

---

## Deterministic Scripts

Scripts perform read-only gate checks. JSON output with explicit pass/fail/missing-gates.

| Script | Purpose | Skill |
|---|---|---|
| `card-spec/scripts/validate_parent_card.py` | Validate parent card metadata before dispatch | `kanban-card-spec` |
| `plan-gate/scripts/check_plan_gate.py` | Validate plan, scope, forbidden actions, and verification strategy before implementation dispatch | `kanban-plan-gate` |
| `partition-check/scripts/check_partition.py` | Validate write/read scope, locks, and concurrency safety before parallel dispatch | `kanban-partition-check` |
| `watch/scripts/check_run_health.py` | Detect dead PID, stale heartbeat, ghost runs, and missing persisted implementation changes | `kanban-watch` |
| `review/scripts/check_review_evidence.py` | Verify review artifact/report/log exists | `kanban-review` |
| `close-gate/scripts/check_close_gate.py` | Verify close-gate prerequisites | `kanban-close-gate` |
| `gitter/scripts/check_gitter_scope.py` | Validate commit scope, safe staging, and push before close-gate | `kanban-gitter` |

Script contract:
- Python 3, JSON output
- Exit `0`: pass, Exit `1`: fail, Exit `2`: usage error
- Safe read-only by default

---

## Architecture

### Skill Categories

- **`kanban-card-spec`** — Workflow schema/business process. Validates card structure, worker eligibility, intake rules.
- **`kanban-plan-gate`** — Planning/dispatch gate. Validates problem statement, scope, forbidden actions, success criteria, and verification strategy before implementation dispatch.
- **`kanban-partition-check`** — Concurrency/scope gate. Validates write/read scope, exclusive locks, and whether parallel work must be serialized.
- **`kanban-watch`** — Runbook/product verification. Detects ghost/stale runs, checks evidence readiness.
- **`kanban-review`** — Code quality/review. Validates REVIEW_PASS/FAIL evidence, prevents dispatch mistakes.
- **`kanban-close-gate`** — Release/CI gate. Classifies close eligibility: pass, pass-with-warnings, fail.
- **`kanban-gitter`** — Commit/push gate. Validates explicit commit scope, safe staging, and push safety before close-gate.

### Runtime vs Workflow Skills

**Runtime skills** (in `card.skills` / `required_skills`):
- `prism-full` — worker-loadable analysis skill

**Workflow/operator skills** (in body metadata only, NOT runtime skills):
- `kanban-card-spec`
- `kanban-plan-gate`
- `kanban-partition-check`
- `kanban-watch`
- `kanban-review`
- `kanban-close-gate`
- `kanban-gitter`

**Rule:** Do NOT put operator skills in `card.skills` field. Worker skill resolver cannot load them.

### Progressive Disclosure Model

1. **SKILL.md** — Trigger: "when to use this skill" + minimal procedure
2. **This index** — Navigation: "where to find deeper context"
3. **gotchas.md** — Incident memory: "what has gone wrong before"
4. **examples/ JSON** — Incident records: "what happened in this specific case"
5. **universal-stage2-policy.json** — Policy flags: "what the enforcement rules are"
6. **scripts/** — Deterministic checks: "automated gate verification"

---

## Quick Reference

```bash
# Validate parent card before dispatch
python3 skills/kanban/card-spec/scripts/validate_parent_card.py \
  --adapter skills/project-adapters/agent-garden/adapter.json \
  --card-json <parent-card.json>

# Validate plan gate before implementation dispatch
python3 skills/kanban/plan-gate/scripts/check_plan_gate.py \
  <plan-gate.json>

# Validate partition safety before parallel implementation dispatch
python3 skills/kanban/partition-check/scripts/check_partition.py \
  <partition-check.json>

# Check run health and optional persistence evidence
python3 skills/kanban/watch/scripts/check_run_health.py \
  --adapter skills/project-adapters/agent-garden/adapter.json \
  --card-json <card.json> \
  --persistence-json <implementation-persistence.json>

# Verify review evidence
python3 skills/kanban/review/scripts/check_review_evidence.py \
  --review-artifact <review-artifact.json>

# Run close-gate
python3 skills/kanban/close-gate/scripts/check_close_gate.py \
  --adapter skills/project-adapters/agent-garden/adapter.json \
  --parent-json <parent.json> \
  --children-json <children.json> \
  --review-artifact <review-artifact.json>

# Validate gitter scope before close-gate
python3 skills/kanban/gitter/scripts/check_gitter_scope.py \
  <gitter.json>
```
