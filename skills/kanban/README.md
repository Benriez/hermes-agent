# Reusable Kanban Operator Skills

**Skill family:** Separates universal Kanban operator procedures from project adapters. Universal skills define invariant gates and forbidden actions. Project adapters provide repo paths, hosts, workers, verification commands, close-gate policy, examples, and known failure modes.

**Prism-full** is mandatory for Stage 2 planning/review/close-gate workflows where adapters require it.

## Universal Skills

| Skill | Category | Trigger |
|---|---|---|
| `kanban-card-spec` | Workflow schema/business process | Create, validate, decompose, or repair parent/child cards |
| `kanban-watch` | Runbook/product verification | Watch runs, detect ghost/stale runs, check evidence readiness |
| `kanban-review` | Code quality/review | Validate REVIEW_PASS/FAIL evidence, prevent dispatch mistakes |
| `kanban-close-gate` | Release/CI gate | Decide close eligibility: pass, pass-with-warnings, fail |

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
- `kanban-watch`
- `kanban-review`
- `kanban-close-gate`

**Rule:** Do NOT put operator skills in `card.skills` field. Worker skill resolver cannot load them → `Unknown skill(s)` crash.

### Project Adapters

Adapters live under `skills/project-adapters/<project_id>/` and are loaded by deterministic scripts via JSON paths.

## Deterministic Scripts

| Script | Skill | Purpose |
|---|---|---|
| `card-spec/scripts/validate_parent_card.py` | `kanban-card-spec` | Validate card metadata before dispatch |
| `watch/scripts/check_run_health.py` | `kanban-watch` | Detect dead PID, stale heartbeat, ghost runs |
| `review/scripts/check_review_evidence.py` | `kanban-review` | Verify review artifact/report/log exists |
| `close-gate/scripts/check_close_gate.py` | `kanban-close-gate` | Verify close-gate prerequisites |

Script contract: Python 3, JSON output, exit `0`=pass / `1`=fail / `2`=usage error.

## Key Policy Reminders

- **Intake parents:** Always use `--initial-status blocked`. Only `prism-full` in runtime skills.
- **`ready` vs `review`:** `ready` = implementation dispatch. `review` = formal review path. `minimax-implementer` must use `review`.
- **Parent done:** Means orchestration/decomposition complete only. Child review + close-gate still required.
- **Direct SQLite:** Rescue-only with operator authorization + artifact evidence.
- **Dispatcher skill guards:** Optional skills must be availability-checked before spawn.
- **Gotchas:** First-class material at `shared/gotchas.md`. Read it when something behaves unexpectedly.
