#!/usr/bin/env python3
"""Check a Hermes Kanban gitter scope JSON object.

Accepts either a flat object containing `gitter` or a wrapped object
containing `{ "task": { "gitter": ... } }`. Emits JSON to stdout.
Exit codes: 0 PASS/WARN, 1 BLOCK, 2 usage/config error.
"""
import argparse
import json
import sys
from pathlib import Path

TASK_KEYS = ["task_id", "adapter", "project", "repo_path", "issue"]
GIT_KEYS = ["branch", "remote", "remote_branch", "head_before", "head_after"]
SCOPE_KEYS = ["files_to_commit", "files_to_exclude", "allow_artifacts",
              "allow_wiki_files", "allow_source_files"]
PLAN_KEYS = ["commit_required", "push_required", "message", "body"]
SAFETY_KEYS = ["force_push_allowed", "github_issue_close_allowed",
               "pr_allowed", "merge_allowed", "direct_sqlite_allowed"]
DECISION_KEYS = ["gitter_allowed", "requires_operator_approval", "reason"]


def load_json(path):
    try:
        return json.loads(Path(path).read_text())
    except Exception as exc:
        print(json.dumps({
            "status": "BLOCK",
            "errors": [f"cannot read/parse JSON: {exc}"],
            "warnings": [],
            "checks": {},
            "decision": {}
        }))
        sys.exit(2)


def unwrap(data):
    if isinstance(data, dict) and isinstance(data.get("gitter"), dict):
        return data["gitter"]
    task = data.get("task") if isinstance(data, dict) else None
    if isinstance(task, dict) and isinstance(task.get("gitter"), dict):
        return task["gitter"]
    return None


def required_keys_present(obj, keys):
    return isinstance(obj, dict) and all(k in obj for k in keys)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json_file", help="Gitter scope JSON file")
    parser.add_argument("--strict", action="store_true",
                        help="Treat warnings as blocking errors")
    args = parser.parse_args()

    data = load_json(args.json_file)
    g = unwrap(data)
    errors = []
    warnings = []
    checks = {}

    if g is None:
        errors.append(
            "missing gitter object "
            "(expected top-level gitter or task.gitter)"
        )
        decision = {}
    else:
        task = g.get("task") or {}
        git_ctx = g.get("git_context") or {}
        scope = g.get("intended_scope") or {}
        plan = g.get("commit_plan") or {}
        safety = g.get("safety") or {}
        decision = g.get("decision") or {}

        checks["task_present"] = required_keys_present(task, TASK_KEYS)
        checks["git_context_present"] = required_keys_present(git_ctx, GIT_KEYS)
        checks["scope_present"] = required_keys_present(scope, SCOPE_KEYS)
        checks["safety_present"] = required_keys_present(safety, SAFETY_KEYS)
        checks["plan_present"] = required_keys_present(plan, PLAN_KEYS)
        checks["decision_present"] = required_keys_present(decision, DECISION_KEYS)

        if not checks["task_present"]:
            errors.append("task missing required fields")
        if not checks["git_context_present"]:
            errors.append("git_context missing required fields")
        if not checks["scope_present"]:
            errors.append("intended_scope missing required fields")
        if not checks["safety_present"]:
            errors.append("safety missing required fields")
        if not checks["plan_present"]:
            errors.append("commit_plan missing required fields")
        if not checks["decision_present"]:
            errors.append("decision missing required fields")

        commit_required = plan.get("commit_required", True)
        files_to_commit = scope.get("files_to_commit") or []
        actual_changed_paths = scope.get("actual_changed_paths")
        expected_changed_paths = scope.get("expected_changed_paths") or files_to_commit
        no_change_task = bool(scope.get("no_change_task") or scope.get("read_only_task"))
        commit_message = plan.get("message")
        allow_artifacts = scope.get("allow_artifacts", False)
        allow_wiki = scope.get("allow_wiki_files", False)
        force_push = safety.get("force_push_allowed", False)
        gh_close = safety.get("github_issue_close_allowed", False)
        pr_allowed = safety.get("pr_allowed", False)
        merge_allowed = safety.get("merge_allowed", False)
        sqlite_allowed = safety.get("direct_sqlite_allowed", False)
        op_approved = decision.get("requires_operator_approval", False)

        if commit_required:
            if not files_to_commit:
                errors.append(
                    "commit_required is true but files_to_commit is empty"
                )
            if not commit_message:
                errors.append(
                    "commit_required is true but commit_message is missing"
                )
            if actual_changed_paths is not None and expected_changed_paths and not actual_changed_paths and not no_change_task:
                errors.append(
                    "commit_required is true but actual_changed_paths is empty for expected changes"
                )
        else:
            if not files_to_commit:
                warnings.append(
                    "commit_required is false and files_to_commit is empty — "
                    "this is acceptable only for explicit no-op/read-only tasks"
                )
            if not no_change_task and not files_to_commit:
                warnings.append(
                    "empty commit scope requires explicit no_change_task/read_only_task classification"
                )

        if force_push and not op_approved:
            errors.append(
                "force_push_allowed is true without operator approval"
            )

        if gh_close and not op_approved:
            errors.append(
                "github_issue_close_allowed is true without operator approval"
            )
        if pr_allowed and not op_approved:
            errors.append(
                "pr_allowed is true without operator approval"
            )
        if merge_allowed and not op_approved:
            errors.append(
                "merge_allowed is true without operator approval"
            )
        if sqlite_allowed:
            errors.append(
                "direct_sqlite_allowed is true — SQLite writes from gitter "
                "are forbidden"
            )

        if allow_artifacts:
            warnings.append(
                "allow_artifacts is true — artifact files should not be "
                "silently committed"
            )
        if allow_wiki:
            warnings.append(
                "allow_wiki_files is true — wiki files should not be "
                "silently committed"
            )

        checks["commit_scope_explicit"] = (
            bool(files_to_commit) if commit_required else True
        )
        checks["commit_message_present"] = (
            bool(commit_message) if commit_required else True
        )
        checks["force_push_disallowed"] = (
            not force_push or bool(op_approved)
        )
        checks["github_mutations_disallowed_by_default"] = (
            not gh_close or bool(op_approved)
        )
        checks["pr_merge_disallowed_by_default"] = (
            (not pr_allowed and not merge_allowed) or bool(op_approved)
        )
        checks["sqlite_disallowed"] = not sqlite_allowed
        checks["decision_allows_gitter"] = decision.get("gitter_allowed") is True

        if decision.get("gitter_allowed") is False:
            errors.append("decision states gitter is not allowed")

    if args.strict and warnings:
        errors.extend([f"strict_warning: {w}" for w in warnings])

    if errors:
        status = "BLOCK"
    elif warnings:
        status = "WARN"
    else:
        status = "PASS"

    out = {
        "status": status,
        "errors": errors,
        "warnings": warnings,
        "checks": checks,
        "decision": decision
    }
    print(json.dumps(out, indent=2))
    sys.exit(1 if status == "BLOCK" else 0)


if __name__ == "__main__":
    main()