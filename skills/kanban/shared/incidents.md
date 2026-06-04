# Kanban Operator Incidents

**Purpose:** Concise index of significant incidents and what they taught us. Each entry: date, title, root cause, canonical fix, references.

---

## Incident Index

### t_02f1e58a — sdlc-review Availability Guard Close-Gate
- **Date:** 2026-06-04
- **Title:** Review dispatch crashed with `Unknown skill(s): sdlc-review`
- **Root cause:** Review dispatch hardcoded `sdlc-review` as required skill without checking availability
- **Canonical fix:** `_resolve_task_skill_in_home()` guard in `_default_spawn`; silently skip missing optional skills
- **Notable:** Review evidence lived in `kanban run` metadata (`review_passed: true`), no separate JSON/TXT files produced
- **Close-gate:** CLOSE_GATE_PASS_WITH_WARNINGS (scratch workspace cleaned, GitHub issue null, `<user>/<branch>` vs assumed origin/<branch> — Agent Garden incident: benriez/bodi)
- **Example:** `../shared/examples/sdlc-review-availability-guard-close-gate-learning.json`
- **Artifacts:** `~/.hermes/artifacts/agent-garden-sdlc-review-*`

### Issue #51 Review Dispatch Learning
- **Date:** 2026-06-03
- **Title:** Formal review routing and evidence gaps
- **Root cause:** Review card left in `ready` status routed through implementation dispatch; `sdlc-review` hardcoded without availability guard
- **Canonical fix:** `review` status required for formal review; `_resolve_task_skill_in_home()` guard
- **Example:** `../shared/examples/issue-51-review-dispatch-learning.json`

### t_50dd31da Intake Auto-Dispatch + Skill Resolution Failure
- **Date:** 2026-06-04
- **Title:** Stage 1 intake parent card auto-dispatched, crashed with `Unknown skill(s): kanban-card-spec, kanban-watch`
- **Root cause 1:** `hermes kanban create` defaults to `ready`; intake parent not created with `--initial-status blocked`
- **Root cause 2:** `kanban-card-spec` and `kanban-watch` placed in card `skills` field (worker runtime); these are operator skills not in worker search path
- **Canonical fix:** Intake parents always use `--initial-status blocked`; only `prism-full` in runtime skills; operator skills in body metadata fields
- **Example:** `../shared/examples/intake-auto-dispatch-skill-resolution-learning.json`
- **Related:** `../../project-adapters/agent-garden/examples/intake-auto-dispatch-skill-resolution-learning.json`

### Run #96 — Ghost/Stale Run
- **Date:** 2026-06-04
- **Title:** Worker dead but DB showed `running`; PID stale
- **Root cause:** Worker process died but dispatcher DB state not updated
- **Canonical fix:** Watch task detects dead PID + stale heartbeat; `kanban reclaim` to reclaim card; dispatcher auto-reclaimed at next tick
- **Reference:** `watch/scripts/check_run_health.py` ghost run detection

### t_20096ee4 — Production Pilot Persistence Failure
- **Date:** 2026-06-04
- **Title:** Implementation completed and review passed, but expected target repo changes were absent
- **Root cause:** Worker summary claimed files were created, but `git diff` showed zero changes in expected allowed paths. Scratch or inaccessible workspace state was treated as success without durable target repo evidence.
- **Canonical fix:** Watch persistence gate classifies this as `implementation_completed_but_no_persisted_changes`; review/gitter/close-gate must require actual target repo diff/content evidence or explicit no-change classification.
- **Artifact:** `~/.hermes/artifacts/kanban-production-v0-1-first-pilot.artifact.json`
- **Reference:** `watch/scripts/check_run_health.py --persistence-json <evidence.json>`

### Issue #48 — Success Workflow Pilot
- **Date:** 2026-06-03
- **Title:** First complete Agent Garden Stage 2 issue
- **Root cause:** Workflow gaps identified: GitHub close before commit, wrong workspace, wrong review worker
- **Canonical fix:** Close gate requires commit + push before close; Pi-local scratch workspace; review worker (Agent Garden: `minimax-implementer`) for review
- **Example:** `../shared/examples/issue-48-success.json`

### Remote Target Ambiguity (Agent Garden: benriez/bodi vs origin/bodi)
- **Date:** 2026-06-04
- **Title:** Close-gate failed by assuming wrong remote
- **Root cause:** Task body referenced `origin/<branch>` but push was to `<user>/<branch>` (user fork)
- **Canonical fix:** Always verify actual remote/branch with `git ls-remote <remote> refs/heads/<branch>`; `origin` = upstream NousResearch, `<user>` = user fork
- **Reference:** `../gotchas.md` — "Remote and Branch Naming" gotcha

---

## Pattern Summary

| Pattern | Symptom | Prevention |
|---|---|---|
| Intake parent auto-dispatch | Card spawned immediately | `--initial-status blocked` |
| Skill resolver crash | `Unknown skill(s): kanban-card-spec` | Only runtime skills in `card.skills` |
| Wrong dispatch path | review worker in `ready` status (Agent Garden: `minimax-implementer`) | Use `review` status for formal review |
| Ghost run | DB `running`, worker dead | Watch + reclaim pattern |
| Missing review evidence | No separate JSON/TXT files | Accept run metadata + agent log |
| Scratch workspace gone | Artifacts inaccessible | Use global `~/.hermes/artifacts/` |
| Completed but no persisted changes | Worker claims success, target repo diff empty | Watch persistence evidence: expected_changed_paths vs actual_changed_paths |
