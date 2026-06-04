#!/usr/bin/env python3
"""Check a Hermes Kanban plan_gate JSON object.

Accepts either a flat object containing `plan_gate` or a wrapped object
containing `{ "task": { "plan_gate": ... } }`. Emits JSON to stdout.
Exit codes: 0 PASS, 1 FAIL, 2 usage/config error.
"""
import argparse
import json
import re
import sys
from pathlib import Path

CONCRETE_WORKER_PATTERN = re.compile(r"(^|[^a-z0-9])([a-z0-9]+-[a-z0-9]+er|[a-z0-9]+-implementer|[a-z0-9]+-reviewer)([^a-z0-9]|$)", re.I)
ALLOWED_ROLE_VALUES = {"implementation_worker", "review_worker", "gitter", "committer", "close_gate_verifier", None}


def load_json(path):
    try:
        return json.loads(Path(path).read_text())
    except Exception as exc:
        print(json.dumps({"status": "FAIL", "errors": [f"cannot read/parse JSON: {exc}"], "warnings": [], "checks": {}}))
        sys.exit(2)


def unwrap_plan(data):
    if isinstance(data, dict) and isinstance(data.get("plan_gate"), dict):
        return data["plan_gate"]
    task = data.get("task") if isinstance(data, dict) else None
    if isinstance(task, dict) and isinstance(task.get("plan_gate"), dict):
        return task["plan_gate"]
    return None


def non_empty_string(value):
    return isinstance(value, str) and bool(value.strip())


def non_empty_list(value):
    return isinstance(value, list) and any(str(item).strip() for item in value)


def has_keys(obj, keys):
    return isinstance(obj, dict) and all(key in obj for key in keys)


def contains_concrete_worker(value):
    if value is None:
        return False
    if isinstance(value, str):
        if value in ALLOWED_ROLE_VALUES:
            return False
        return bool(CONCRETE_WORKER_PATTERN.search(value))
    if isinstance(value, list):
        return any(contains_concrete_worker(v) for v in value)
    if isinstance(value, dict):
        return any(contains_concrete_worker(v) for v in value.values())
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json_file", help="Plan gate JSON file")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as failures")
    args = parser.parse_args()

    data = load_json(args.json_file)
    plan = unwrap_plan(data)
    errors = []
    warnings = []

    if plan is None:
        errors.append("missing plan_gate object (expected top-level plan_gate or task.plan_gate)")
        checks = {}
    else:
        scope = plan.get("scope")
        verification = plan.get("verification_strategy")
        dispatch = plan.get("dispatch_decision")
        risk = plan.get("risk_assessment")
        adapter_context = plan.get("adapter_context")

        checks = {
            "problem_statement_present": non_empty_string(plan.get("problem_statement")),
            "operator_intent_present": non_empty_string(plan.get("operator_intent")),
            "success_criteria_non_empty": non_empty_list(plan.get("success_criteria")),
            "non_goals_present": isinstance(plan.get("non_goals"), list),
            "forbidden_actions_present": non_empty_list(plan.get("forbidden_actions")),
            "scope_present": has_keys(scope, ["allowed_paths", "forbidden_paths", "affected_systems"]),
            "adapter_context_present": has_keys(adapter_context, ["adapter", "project", "repo_path", "issue"]),
            "execution_plan_non_empty": non_empty_list(plan.get("execution_plan")),
            "verification_strategy_present": has_keys(verification, ["commands", "manual_checks", "evidence_expected"]),
            "verification_evidence_expected_non_empty": isinstance(verification, dict) and non_empty_list(verification.get("evidence_expected")),
            "risk_assessment_present": has_keys(risk, ["risk_level", "known_risks", "rollback_or_recovery"]),
            "dispatch_decision_present": has_keys(dispatch, ["ready_for_implementation", "required_worker_role", "requires_operator_approval", "reason"]),
            "uses_worker_roles_not_concrete_names": not contains_concrete_worker(dispatch.get("required_worker_role") if isinstance(dispatch, dict) else None),
        }

        required_fail_checks = [
            "problem_statement_present",
            "operator_intent_present",
            "success_criteria_non_empty",
            "forbidden_actions_present",
            "scope_present",
            "execution_plan_non_empty",
            "verification_strategy_present",
            "verification_evidence_expected_non_empty",
            "dispatch_decision_present",
            "uses_worker_roles_not_concrete_names",
        ]
        for check in required_fail_checks:
            if not checks.get(check):
                errors.append(check)

        if checks.get("dispatch_decision_present") and isinstance(dispatch, dict):
            role = dispatch.get("required_worker_role")
            if role not in ALLOWED_ROLE_VALUES:
                warnings.append(f"required_worker_role is not a known universal role: {role}")
            if dispatch.get("ready_for_implementation") is True and not dispatch.get("reason"):
                errors.append("dispatch_decision.reason required when ready_for_implementation is true")

        if args.strict and warnings:
            errors.extend([f"strict_warning: {w}" for w in warnings])

    status = "PASS" if not errors else "FAIL"
    print(json.dumps({"status": status, "errors": errors, "warnings": warnings, "checks": checks}, indent=2))
    sys.exit(0 if status == "PASS" else 1)


if __name__ == "__main__":
    main()
