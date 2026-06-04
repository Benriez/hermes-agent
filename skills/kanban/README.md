# Reusable Kanban Operator Skills

**Skill family:** Separates universal Kanban operator procedures from project adapters. Universal skills define invariant gates and forbidden actions. Project adapters provide repo paths, hosts, workers, verification commands, close-gate policy, examples, and known failure modes.

**Prism-full** is mandatory for Stage 2 planning/review/close-gate workflows where adapters require it.

## Universal Skills

| Skill | Category | Trigger |
|---|---|---|
| `kanban-card-spec` | Workflow schema/business process | Create, validate, decompose, or repair parent/child cards |
| `kanban-plan-gate` | Planning/dispatch gate | Validate plan, scope, forbidden actions, and verification strategy before implementation dispatch |
| `kanban-partition-check` | Concurrency/scope gate | Validate disjoint write scope, locks, and concurrency safety before parallel dispatch |
| `kanban-watch` | Runbook/product verification | Watch runs, detect ghost/stale runs, check evidence readiness |
| `kanban-review` | Code quality/review | Validate REVIEW_PASS/FAIL evidence, prevent dispatch mistakes |
| `kanban-close-gate` | Release/CI gate | Decide close eligibility: pass, pass-with-warnings, fail |
| `kanban-gitter` | Commit/push gate | Validate explicit commit scope, safe staging, and push before close-gate |

## Architecture

### Skill Folder Structure
Each skill is a **folder** containing:
- `SKILL.md` — trigger description + minimal procedure + progressive disclosure links
- `scripts/` — deterministic gate-check scripts
- (optional) `examples/` — task-specific examples

```
skills/kanban/<skill>/
  SKILL.md
  scripts/<check_script>.py
```

### Progressive Disclosure Model

1. **SKILL.md** — "When to use this skill" trigger + minimal steps
2. **`shared/index.md`** — Navigation to deeper files
3. **`shared/gotchas.md`** — Incident memory: what has gone wrong
4. **`shared/examples/`** — JSON incident records: what happened
5. **`shared/universal-stage2-policy.json`** — Policy flags and enforcement rules
6. **`scripts/`** — Deterministic automated gate checks

**Rule:** SKILL.md files stay focused. Detailed gotcha lists, example dumps, and policy flags live in linked files.

### Runtime vs Workflow Skills

**Worker runtime skills** (in `card.skills` / `required_skills`):
- `prism-full` — worker-loadable analysis skill

**Workflow/operator skills** (body metadata only, NOT runtime skills):
- `kanban-card-spec`
- `kanban-plan-gate`
- `kanban-partition-check`
- `kanban-watch`
- `kanban-review`
- `kanban-close-gate`

**Rule:** Do NOT put operator skills in `card.skills` field. Worker skill resolver cannot load them → `Unknown skill(s)` crash.

### Project Adapters

Adapters live under `skills/project-adapters/<project_id>/` and are loaded by deterministic scripts via JSON paths.

## Inner-Loop Workflow Sequence

1. `kanban-card-spec` — validate card structure and workflow/runtime skill separation.
2. `kanban-plan-gate` — validate plan, success criteria, non-goals, forbidden actions, scope, and verification strategy.
3. `kanban-partition-check` — validate write/read scope, locks, and concurrency safety before parallel implementation dispatch.
4. Implementation dispatch — adapter-declared implementation worker.
5. `kanban-watch` — monitor run health and evidence readiness.
6. `kanban-review` — validate review evidence and REVIEW_PASS/FAIL.
7. `kanban-gitter` — validate commit scope, safe staging, and push before close-gate.
8. `kanban-close-gate` — decide close eligibility.
9. Record learning — update gotchas/incidents/examples when requested.

## Deterministic Scripts

| Script | Skill | Purpose |
|---|---|---|
| `card-spec/scripts/validate_parent_card.py` | `kanban-card-spec` | Validate card metadata before dispatch |
| `plan-gate/scripts/check_plan_gate.py` | `kanban-plan-gate` | Validate implementation plan, scope, forbidden actions, and verification strategy |
| `partition-check/scripts/check_partition.py` | `kanban-partition-check` | Validate write/read scope, locks, and concurrency safety before parallel dispatch |
| `watch/scripts/check_run_health.py` | `kanban-watch` | Detect dead PID, stale heartbeat, ghost runs, and missing persisted implementation changes |
| `review/scripts/check_review_evidence.py` | `kanban-review` | Verify review artifact/report/log exists |
| `close-gate/scripts/check_close_gate.py` | `kanban-close-gate` | Verify close-gate prerequisites |
| `gitter/scripts/check_gitter_scope.py` | `kanban-gitter` | Validate commit scope, safe staging, and push before close-gate |

Script contract: Python 3, JSON output, exit `0`=pass / `1`=fail / `2`=usage error.

## Key Policy Reminders

- **Intake parents:** Always use `--initial-status blocked`. Only `prism-full` in runtime skills.
- **Plan gate:** Before ambiguous or risky implementation dispatch, require a plan with success criteria, non-goals, forbidden actions, bounded scope, and verification strategy.
- **Partition check:** Before parallel implementation dispatch, require explicit disjoint write scope or operator-approved serialization for conflicts.
- **Gitter:** Before close-gate when commits are expected, require explicit files_to_commit and block force-push, GitHub mutations, and SQLite writes by default.
- **Persistence:** Implementation completion is not enough. If writes are expected, watch/review/gitter/close-gate require actual target repo diff/content evidence or explicit no-change classification.
- **`ready` vs `review`:** `ready` = implementation dispatch. `review` = formal review path. Review worker (Agent Garden adapter: `minimax-implementer`) must use `review`.
- **Parent done:** Means orchestration/decomposition complete only. Child review + close-gate still required.
- **Direct SQLite:** Rescue-only with operator authorization + artifact evidence.
- **Dispatcher skill guards:** Optional skills must be availability-checked before spawn.
- **Gotchas:** First-class material at `shared/gotchas.md`. Read it when something behaves unexpectedly.
