# Kanban Shared Gotchas

Known failure modes, edge cases, and non-obvious behaviors discovered through incident history.

---

## Skill Availability Guards

### Optional Review Skills Must Be Availability-Guarded

**Gotcha:** Review dispatch hardcoding `sdlc-review` as a required skill crashes the worker with `Unknown skill(s): sdlc-review` when the skill is not installed.

**Pattern:** Use `_resolve_task_skill_in_home()` (or equivalent skill availability check) before passing `--skills` to the worker CLI. Silently skip missing optional skills rather than failing the spawn.

**Correct pattern (from `hermes_cli/kanban_db.py` `_default_spawn`):**
```python
if not _resolve_task_skill_in_home(env.get("HERMES_HOME"), sk):
    # Skill not available — skip silently so a missing/disabled skill
    # does not crash the worker at CLI startup (ValueError: Unknown skill(s))
    continue
```

**Source incident:** Issue #51 run 88 crashed with `Unknown skill(s): sdlc-review`; t_50dd31da run 90 crashed with `Unknown skill(s): kanban-card-spec, kanban-watch`.

**Reference:** `skills/kanban/shared/failure-modes.md` — "Review dispatch hardcoded sdlc-review without an availability guard"

---

## Review Evidence Patterns

### Review Evidence May Live in Run Metadata, Not Separate Artifacts

**Gotcha:** `minimax-implementer` review agents sometimes record `REVIEW_PASS` in the Kanban run metadata (`review_passed: true` + structured summary) without producing separate `review-report.json` / `review-report.txt` artifact files.

**Rule:** Close-gate and watch tasks must accept `kanban run --json` metadata + agent log + watch artifact as sufficient evidence of REVIEW_PASS when the explicit `review_passed: true` field is present and the summary confirms the review.

**Do NOT fail a close-gate or watch task only because the separate review JSON/TXT files are absent.**

**Reference workflow:** t_02f1e58a — run #99 minimax-implementer review recorded `review_passed: true` in run metadata. Separate review artifacts were not produced. Close-gate accepted run metadata + agent log as proof.

---

## Workspace Lifecycle

### Scratch Workspace May Be Cleaned After Task Completion

**Gotcha:** Kanban scratch workspaces (under `workspaces/<card-id>/`) are cleaned by the workspace lifecycle after task completion. Implementation artifacts (test logs, reports) stored only in the scratch workspace become inaccessible after the task closes.

**Rule:** For close-gate purposes, scratch workspace cleanup is a **warning, not a failure**, if globally durable evidence exists:
- Commit hash on remote
- Global artifacts directory (`~/.hermes/artifacts/`)
- Kanban run metadata
- Agent log with explicit REVIEW_PASS

**Do NOT make scratch workspace files the only source of close-gate evidence.**

**Remedy:** Copy implementation artifacts to `~/.hermes/artifacts/` before a task completes, or ensure the task produces artifacts in a persistent global path.

---

## Remote and Branch Naming

### Do Not Assume `origin/bodi` — Verify the Actual Remote

**Gotcha:** Tasks may reference `origin/bodi` in their body/policy but the actual committed branch is `benriez/bodi` (user's fork), not `origin/bodi` (NousResearch upstream).

**Rule:** Always verify the actual remote and branch from the task's git operations. Close-gate must check `git ls-remote <remote> refs/heads/<branch>` to confirm the commit exists on the **actual** remote.

**In `benriez/hermes-agent` context:** `origin` = NousResearch/hermes-agent (upstream), `benriez` = Benriez/hermes-agent (user fork). The bodi branch was created on `benriez`, not `origin`.

**Do NOT mark a close-gate as failed because the commit is on `benriez/bodi` instead of `origin/bodi` — verify against the actual remote target.**

**Reference workflow:** t_02f1e58a — commit 30ed778ec pushed to `benriez/bodi` (new branch), not `origin/bodi`.

---

## GitHub Issue Handling

### Internal Follow-up Cards Have No GitHub Issue

**Gotcha:** Some follow-up cards are created from intake orchestration cards and do not have a GitHub issue number (`github.issue_number: null`). These are internal workflow continuations, not GitHub-linked issues.

**Rule:** When `github.issue_number` is `null`, GitHub close is **not applicable**. Close-gate should classify this as `github_close_not_applicable` (warning, not failure). Do not require a GitHub issue to exist for internal follow-up cards.

**Reference workflow:** t_02f1e58a — internal follow-up with `issue_number: null`. Close-gate passed with `github_close_not_applicable_without_explicit_issue`.

---

## Dirty Working Tree

### Unrelated Dirty Files Are Not a Close-Gate Failure

**Gotcha:** The Hermes working tree on the Pi may have many unrelated dirty/modified files from prior experiments, feature branches, or unfinished work.

**Rule:** Close-gate should verify that **intended files were committed** and **unrelated files were NOT staged or committed**. The presence of unrelated dirty files in the working tree is not a failure — only verify staged/committed scope.

**Reference:** `git status --short` and `git diff --cached --name-only` are the correct verification commands, not the overall dirty state.

---

## Role Responsibility Separation

### Gitter/Committer Is a Separate Role from Implementer

**Gotcha:** The implementation → commit/push workflow may have different agents for each step. The implementer produces evidence; the gitter/committer creates the commit and push. These should be explicit role assignments.

**Rule:** When a task requires commit/push, the workflow should explicitly assign gitter/committer responsibility separate from the implementer. The implementer's job is to produce correct code and evidence; the gitter's job is to verify and commit/push.

**Reference:** `universal-stage2-policy.json` — `gitter_role_explicit_for_commit_push: true`.

---

## Close-Gate Pass-with-Warnings Is Valid

**Gotcha:** Close-gate may legitimately pass with non-critical warnings (e.g., scratch workspace cleaned, no separate review artifacts, GitHub issue number null, unrelated dirty files present) while all core gates remain satisfied.

**Rule:** `CLOSE_GATE_PASS_WITH_WARNINGS` is a valid and correct classification when:
- All core gates pass (parent done, child done, REVIEW_PASS, commit on remote, no PR/merge)
- Only non-critical environmental warnings exist

**Do NOT require zero warnings for a passing close-gate.** The warnings must be evaluated for severity.

---

## Dispatch Semantics: Review vs Ready Status

### `ready` Routes Through Implementation Dispatch; `review` Routes Through Formal Review

**Gotcha:** Assigning `minimax-implementer` to a card in `ready` status routes it through the implementation dispatch path, which blocks `minimax-implementer` as an implementation worker.

**Rule:** Formal review requires card status `review`, not `ready`. The `kanban promote` command transitions `blocked → ready`; a separate mechanism or official CLI command transitions `ready → review`. Direct SQLite writes for this transition were a rescue operation and must not become normal workflow.

**Reference:** `skills/kanban/shared/failure-modes.md` — "Review card assigned to minimax-implementer but left in ready status is routed through implementation dispatch"

---

## Workflow Metadata Fields

### `card.skills` Means Worker Runtime Skills, Not Workflow Metadata

**Gotcha:** Intake parent cards may incorrectly include operator/documentation skills (e.g., `kanban-card-spec`, `kanban-watch`) in the `card.skills` field. These are not worker-executable skills — they are workflow metadata.

**Rule:** Worker runtime skills must be in `card.skills` (or `required_worker_skills` in body). Workflow metadata must be in separate body fields (`workflow_skill`, `operator_skills_used`). Do not attach operator skills as worker-required skills.

**Reference:** `universal-stage2-policy.json` — `intake_parent_cards.card_skills_field_means_worker_runtime_skills`

---

## Evidence Cross-References

### Source Workflow for This Gotchas Document

- **Parent card:** t_50dd31da (Stage 1 Intake — Review dispatch sdlc-review availability guard)
- **Child card:** t_02f1e58a ([Follow-up] Fix review dispatch sdlc-review availability guard)
- **Implementation run:** #97 (deep-implementer)
- **Review run:** #99 (minimax-implementer, REVIEW_PASS)
- **Commit:** 30ed778ec46b806079e8cebf1be11503c77ae0b6
- **Remote:** benriez/bodi
- **Close-gate artifact:** `~/.hermes/artifacts/agent-garden-sdlc-review-availability-guard-close-gate.artifact.json`
- **Review watch artifact:** `~/.hermes/artifacts/agent-garden-sdlc-review-availability-guard-review-run-99-watch.artifact.json`
- **Failure modes:** `skills/kanban/shared/failure-modes.md`
- **Policy:** `skills/kanban/shared/universal-stage2-policy.json`
