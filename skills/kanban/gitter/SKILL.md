---
name: kanban-gitter
description: "Use this skill when a completed Kanban implementation/review needs commit-scope validation, safe staging, commit/push evidence, or confirmation that no unrelated files were committed before close-gate."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [kanban, operator, gitter, commit, push, prism-full]
    related_skills: [prism-full]
---

# Kanban Gitter

## Overview
Validates that a completed task's git commit and push are safe, scoped, and don't include unrelated or forbidden changes. The goal is to prevent accidental inclusion of artifacts, wiki files, dirty untracked files, or force-pushes in the task evidence. This skill is universal: it uses task/adapter context and explicit scope lists; concrete remotes, branches, and repo paths belong to adapters or task context.

## When to Use
- Before close-gate when the task produced files that need committing and pushing.
- Before marking implementation done if the task changed repository files.
- When verifying that a worker's staged files are exactly the intended task scope.
- When confirming that a push reached the expected remote branch.

## When Not to Use
- For pure read-only tasks that produced no repository changes.
- For documentation-only tasks where operator explicitly chose no commit.
- For tasks where no files were modified and the task body already records explicit `no_change_task` / read-only classification.

## Required Gitter Fields
A valid `gitter` gate must include:
- `task` identity (task_id, adapter, project, repo_path, issue)
- `git_context` (branch, remote, remote_branch, head_before, head_after)
- `intended_scope` (files_to_commit, files_to_exclude, allow_artifacts, allow_wiki_files, allow_source_files)
- `commit_plan` (commit_required, push_required, message, body)
- `safety` flags (force_push_allowed, github_issue_close_allowed, pr_allowed, merge_allowed, direct_sqlite_allowed)
- `decision` (gitter_allowed, requires_operator_approval, reason)

## Pass Criteria
- `files_to_commit` is explicitly non-empty when `commit_required` is true.
- `commit_message` is present when `commit_required` is true.
- `force_push_allowed` is false (or explicitly operator-approved).
- All safety flags (`github_issue_close_allowed`, `pr_allowed`, `merge_allowed`, `direct_sqlite_allowed`) are false unless explicitly operator-approved.
- `allow_artifacts` and `allow_wiki_files` are false unless explicitly needed by the task.
- `decision` explicitly states whether gitter is allowed and whether operator approval is required.

## Warn Criteria
- `allow_artifacts` or `allow_wiki_files` is true — these should not be silently included.
- `files_to_exclude` is empty and there are known artifact/wiki paths in the repo.

## Fail/Block Criteria
- `commit_required` is true but `files_to_commit` is empty or missing.
- `commit_required` is true but `commit_message` is missing.
- `commit_required` is true and provided `actual_changed_paths` is empty for expected changes, unless explicitly classified as a no-change/read-only task.
- `force_push_allowed` is true without explicit operator approval.
- Any safety flag (`github_issue_close_allowed`, `pr_allowed`, `merge_allowed`, `direct_sqlite_allowed`) is true without explicit operator approval.
- `decision` is missing or does not state whether gitter is allowed.

## Relationship to Other Kanban Skills
- **card-spec:** validates card structure and runtime/workflow skill separation.
- **plan-gate:** validates that the implementation plan is correct before dispatch.
- **partition-check:** validates that concurrent plans don't conflict.
- **watch:** monitors active runs and detects ghost/stale runs.
- **review:** verifies completed implementation evidence and REVIEW_PASS/FAIL.
- **gitter:** validates that committed and pushed changes are safe and scoped before close-gate.
- **close-gate:** decides whether completed/reviewed work can be closed or released after gitter evidence is confirmed.

## Deterministic Script
- `scripts/check_gitter_scope.py <gitter.json>`

## Progressive Disclosure
- **Full index:** `../shared/index.md`
- **Gotchas:** `../shared/gotchas.md`
- **Policy:** `../shared/universal-stage2-policy.json`
- **Checker:** `scripts/check_gitter_scope.py`
- **Examples:** `examples/`

## Forbidden Actions
- Do not use `git add .` or `git add -A` for Kanban gitter flow — always stage explicit paths.
- Do not force push unless `force_push_allowed` is true and operator has explicitly approved.
- Do not close GitHub issues from gitter — close-gate and operator approval are required separately.
- Do not create PRs or merge branches from gitter without explicit operator approval.
- Do not direct-write SQLite from gitter.
- Do not dispatch workers from this skill.
- Do not encode adapter concrete worker names, remotes, or branch names into universal policy or examples.

## Next Skill Handoff
- PASS: close-gate may proceed if all other gates pass.
- WARN: operator must review the warning before proceeding.
- BLOCK: fix the gitter scope before close-gate.