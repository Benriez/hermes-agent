# Kanban Operator Gotchas

**Purpose:** First-class incident memory for Kanban operator workflows. Each gotcha documents: symptom, cause, canonical fix, and related references.

**How to use:** When something behaves unexpectedly in a Kanban workflow, search this file. Each gotcha is self-contained.

---

## Dispatch State Gotchas

### `ready` Routes Through Implementation; `review` Routes Through Formal Review

**Symptom (Agent Garden adapter example):** `minimax-implementer` assigned to a card in `ready` status is routed through implementation dispatch and blocked.

**Cause:** The dispatcher treats `ready` as an implementation signal, not a review signal.

**Rule:** Formal review requires card status `review`, not `ready`. Use official CLI to transition. Direct SQLite writes for this transition were rescue-only.

**Universal principle:** `ready` = implementation dispatch. `review` = formal review path. A review worker (Agent Garden: `minimax-implementer`; other adapters may differ) must use `review` status, not `ready`.

**Canonical fix:** Use `hermes kanban --board <board> move-to-review <card>` when available, or `edit --status review`.

---

### Wrong Problem Solved Correctly Because Plan Gate Was Missing

**Symptom:** Implementation worker reports success, but the changed system, files, or verification target do not match the operator's real intent.

**Cause:** The card was dispatchable before it had an explicit plan gate: problem statement, success criteria, non-goals, forbidden actions, bounded scope, and verification strategy were not reviewable before implementation.

**Rule:** Do not dispatch ambiguous or risky implementation work without a plan gate. Universal plan gates use worker roles and adapter context; concrete worker names remain adapter policy.

**Canonical fix:** Create or validate `plan_gate` first and run `skills/kanban/plan-gate/scripts/check_plan_gate.py <plan-gate.json>` before implementation dispatch.

---

### Parent Done Means Orchestration Complete, Not Issue Complete

**Symptom:** Parent card marked `done` but child evidence, review, and close-gate still required.

**Cause:** `parent done` in Hermes means orchestration/decomposition setup is complete. The GitHub issue remains open until child review + close-gate + operator-approved GitHub close.

**Rule:** Only mark parent `done` after child creation and successful intake/decomposition. Child execution, review, and close-gate proceed independently.

**Reference:** `universal-stage2-policy.json` — parent dependency semantics.

---

## Intake Gotchas

### Intake Parent Cards Must Use `--initial-status blocked`

**Symptom:** Intake parent card auto-dispatched immediately after creation.

**Cause:** `hermes kanban create` defaults to `ready` status when `--initial-status` is not specified.

**Rule:** Always create intake parent cards with `--initial-status blocked`. This prevents auto-dispatch until explicitly approved.

**Canonical fix:**
```bash
hermes kanban --board agent-garden create \
  --title "Stage 1 Intake — <issue>" \
  --initial-status blocked \
  --skills prism-full \
  --body "<body with workflow metadata>"
```

**Reference:** `intake-auto-dispatch-skill-resolution-learning.json`

---

### `card.skills` Field Means Worker Runtime Skills Only

**Symptom:** Worker crashes with `Unknown skill(s): kanban-card-spec, kanban-watch` at startup.

**Cause:** Operator/workflow skills (`kanban-card-spec`, `kanban-watch`, `kanban-review`, `kanban-close-gate`) were placed in `card.skills` field. These are not in the worker skill search path.

**Rule:** Only worker-loadable runtime skills belong in `card.skills` (e.g., `prism-full`). Operator skills are workflow metadata; put them in body fields: `workflow_skill: kanban-card-spec`, `operator_skills_used: [...]`.

**Forbidden in runtime skills:** `kanban-card-spec`, `kanban-watch`, `kanban-review`, `kanban-close-gate`.

**Reference:** `universal-stage2-policy.json` — `intake_parent_cards.card_skills_field_means_worker_runtime_skills`

---

## Review Gotchas

### Optional Review Skills Must Be Availability-Guarded

**Symptom:** Review worker crashes with `Unknown skill(s): sdlc-review`.

**Cause:** Review dispatch hardcodes `sdlc-review` as a required skill without checking availability.

**Pattern:** Use `_resolve_task_skill_in_home()` before passing `--skills` to worker CLI. Silently skip missing optional skills rather than failing the spawn.

**Canonical fix:**
```python
if not _resolve_task_skill_in_home(env.get("HERMES_HOME"), sk):
    # skip silently so missing skill does not crash worker
    continue
```

**Reference:** `hermes_cli/kanban_db.py` `_default_spawn` lines 7944-7950

---

### Review Evidence May Live in Run Metadata, Not Separate Artifacts

**Symptom:** Close-gate or watch task finds no `review-report.json`/`review-report.txt` files.

**Cause:** Agent Garden's `minimax-implementer` review agent may record `REVIEW_PASS` in Kanban run metadata (`review_passed: true` + structured summary) without producing separate artifact files.

**Rule:** Accept `kanban run --json` metadata + agent log + watch artifact as sufficient evidence when `review_passed: true` and summary confirms review. Missing separate review files is a warning, not automatic failure.

**Reference workflow:** t_02f1e58a — run #99 accepted `review_passed: true` in metadata.

---

## Close-Gate Gotchas

### Scratch Workspace Cleanup Is a Warning, Not a Failure

**Symptom:** Close-gate cannot find implementation artifacts in `workspaces/<card-id>/`.

**Cause:** Scratch workspaces are cleaned by lifecycle after task completion.

**Rule:** Scratch workspace cleanup is a warning when globally durable evidence exists:
- Commit hash on remote
- Global artifacts (`~/.hermes/artifacts/`)
- Kanban run metadata with `review_passed: true`
- Agent log confirming review

**Do NOT:** Make scratch workspace the only close-gate evidence source. Copy artifacts to `~/.hermes/artifacts/` before task closes.

---

### Remote Target Must Be Verified Against Actual Remote

**Symptom:** Close-gate fails because commit appears to be on wrong remote/branch.

**Cause:** Task body may reference `origin/bodi` but actual push was to `benriez/bodi` (user fork).

**Rule:** Always verify actual remote/branch from git operations. Check `git ls-remote <remote> refs/heads/<branch>` to confirm commit exists on actual target.

**In benriez/hermes-agent context:** `origin` = NousResearch (upstream), `benriez` = Benriez (user fork). Branch `bodi` was created on `benriez`, not `origin`.

---

### `github.issue_number: null` Means GitHub Close Not Applicable

**Symptom:** Close-gate or operator expects a GitHub issue number that does not exist.

**Cause:** Internal follow-up cards created from intake orchestration have no GitHub issue.

**Rule:** When `github.issue_number` is `null`, GitHub close is not applicable. Record `github_close_not_applicable`. This is not a failure.

**Reference workflow:** t_02f1e58a — internal follow-up with `issue_number: null`.

---

### Unrelated Dirty Files Are Not a Close-Gate Failure

**Symptom:** Close-gate reviewer panics about unrelated dirty files in working tree.

**Cause:** The Hermes working tree may have many unrelated dirty files from prior experiments.

**Rule:** Verify that intended files WERE committed and unrelated files WERE NOT staged/committed. Use `git diff --cached --name-only` to check staged scope. Dirty working tree state alone is not a failure.

---

### `CLOSE_GATE_PASS_WITH_WARNINGS` Is a Valid Classification

**Symptom:** Operator hesitates to accept close-gate with any warnings.

**Rule:** `CLOSE_GATE_PASS_WITH_WARNINGS` is correct when all core gates pass:
- parent done ✓
- child done ✓
- REVIEW_PASS ✓
- commit on remote ✓
- no PR/merge ✓

Only non-critical environmental warnings exist. Evaluate warnings for severity; do not require zero warnings.

---

## Recovery Gotchas

### Direct SQLite Is Rescue-Only

**Symptom:** Operator uses direct SQLite writes as normal workflow path.

**Rule:** Direct SQLite edits are `RESCUE-ONLY`. Require explicit operator authorization + artifact evidence. Must not become normal workflow. Use official Hermes/Kanban CLI status transitions.

---

### Ghost/Stale Runs Can Leave DB Running While Worker Is Dead

**Symptom:** Worker is dead but DB shows `running`; PID is stale.

**Rule:** Detect dead PID + stale heartbeat + wrong workspace. Reclaim with `kanban reclaim`. Do not retry ghost failures endlessly. Watch tasks should detect this pattern.

**Reference:** `scripts/check_run_health.py`

---

## Evidence Cross-References

### Source Workflow (Agent Garden incident evidence)

- **Parent card:** t_50dd31da (Stage 1 Intake, Agent Garden board)
- **Child card:** t_02f1e58a (Follow-up — sdlc-review availability guard)
- **Implementation run:** #97 (Agent Garden: deep-implementer)
- **Review run:** #99 (Agent Garden: minimax-implementer, REVIEW_PASS)
- **Commit:** `30ed778ec` on `<remote>/<branch>` (Agent Garden incident: benriez/bodi)
- **Close-gate:** CLOSE_GATE_PASS_WITH_WARNINGS

### Related Files

- **Failure modes:** `skills/kanban/shared/failure-modes.md`
- **Policy:** `skills/kanban/shared/universal-stage2-policy.json`
- **Examples:** `skills/kanban/shared/examples/sdlc-review-availability-guard-close-gate-learning.json`
- **Artifacts:** `~/.hermes/artifacts/` (agent-garden-sdlc-review-*)

### Incident History

| Incident | Symptom | Fix |
|---|---|---|
| Issue #51 run 88 | `Unknown skill(s): sdlc-review` | Availability guard in `_default_spawn` |
| t_50dd31da run 90 | Auto-dispatched parent, `Unknown skill(s): kanban-card-spec, kanban-watch` | `--initial-status blocked` + `prism-full` only in runtime skills |
| Run #96 | Ghost run, worker dead, DB still running | Watch + reclaim pattern |
| t_02f1e58a review | No separate review JSON/TXT | Accept run metadata + agent log as evidence |
