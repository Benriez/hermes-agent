#!/usr/bin/env python3
"""Check a Hermes Kanban partition_check JSON object.

Accepts either a flat object containing `partition_check` or a wrapped object
containing `{ "task": { "partition_check": ... } }`. Emits JSON to stdout.
Exit codes: 0 PASS/WARN, 1 BLOCK, 2 usage/config error.
"""
import argparse
import json
import sys
from pathlib import Path

WORK_KEYS = [
    "task_id", "adapter", "project", "repo_path", "worker_role", "operation_type",
    "allowed_paths", "forbidden_paths", "read_only_paths", "write_paths",
    "affected_systems", "exclusive_locks", "shared_read_locks",
]
RULE_KEYS = [
    "write_write_conflict_blocks", "write_read_conflict_warns", "exclusive_lock_conflict_blocks",
    "same_repo_unspecified_scope_warns", "unknown_scope_blocks_or_requires_operator", "adapter_may_override",
]
DECISION_KEYS = ["concurrency_allowed", "requires_serial_execution", "requires_operator_approval", "reason"]


def load_json(path):
    try:
        return json.loads(Path(path).read_text())
    except Exception as exc:
        print(json.dumps({"status": "BLOCK", "errors": [f"cannot read/parse JSON: {exc}"], "warnings": [], "conflicts": [], "checks": {}, "decision": {}}))
        sys.exit(2)


def unwrap(data):
    if isinstance(data, dict) and isinstance(data.get("partition_check"), dict):
        return data["partition_check"]
    task = data.get("task") if isinstance(data, dict) else None
    if isinstance(task, dict) and isinstance(task.get("partition_check"), dict):
        return task["partition_check"]
    return None


def as_list(value):
    return value if isinstance(value, list) else []


def norm_path(path):
    return str(path).strip().rstrip("/")


def path_overlaps(a, b):
    a = norm_path(a); b = norm_path(b)
    if not a or not b:
        return False
    if a == b:
        return True
    return a.startswith(b + "/") or b.startswith(a + "/")


def any_path_overlap(left, right):
    overlaps = []
    for a in as_list(left):
        for b in as_list(right):
            if path_overlaps(a, b):
                overlaps.append({"candidate_path": a, "active_path": b})
    return overlaps


def same_repo(candidate, active):
    return bool(candidate.get("repo_path")) and candidate.get("repo_path") == active.get("repo_path")


def required_keys_present(obj, keys):
    return isinstance(obj, dict) and all(k in obj for k in keys)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json_file", help="Partition check JSON file")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as blocking conflicts")
    args = parser.parse_args()

    data = load_json(args.json_file)
    pc = unwrap(data)
    errors = []
    warnings = []
    conflicts = []
    checks = {}

    if pc is None:
        errors.append("missing partition_check object (expected top-level partition_check or task.partition_check)")
        decision = {}
    else:
        candidate = pc.get("candidate")
        active_work = pc.get("active_work")
        rules = pc.get("rules") or {}
        decision = pc.get("decision") or {}

        checks["candidate_present"] = required_keys_present(candidate, WORK_KEYS)
        checks["active_work_checked"] = isinstance(active_work, list)
        checks["rules_present"] = required_keys_present(rules, RULE_KEYS)
        checks["decision_present"] = required_keys_present(decision, DECISION_KEYS)

        if not checks["candidate_present"]:
            errors.append("candidate missing required work scope fields")
        if not checks["active_work_checked"]:
            errors.append("active_work must be a list")
        if not checks["rules_present"]:
            errors.append("rules missing required conflict fields")
        if not checks["decision_present"]:
            errors.append("decision missing required fields")

        ww_conflicts = []
        wr_conflicts = []
        lock_conflicts = []
        unknown_scope = False
        same_repo_unspecified = []

        if checks["candidate_present"] and checks["active_work_checked"]:
            candidate_write = as_list(candidate.get("write_paths"))
            if not candidate_write:
                unknown_scope = True

            for active in active_work:
                if not isinstance(active, dict):
                    warnings.append("active_work entry is not an object")
                    continue
                active_write = as_list(active.get("write_paths"))
                active_read = as_list(active.get("read_only_paths"))
                if same_repo(candidate, active) and (not candidate_write or not active_write):
                    same_repo_unspecified.append({"active_task_id": active.get("task_id"), "repo_path": candidate.get("repo_path")})
                for hit in any_path_overlap(candidate_write, active_write):
                    ww_conflicts.append({"type": "write_write_path_overlap", "active_task_id": active.get("task_id"), **hit})
                for hit in any_path_overlap(candidate_write, active_read):
                    wr_conflicts.append({"type": "write_read_path_overlap", "active_task_id": active.get("task_id"), **hit})
                for lock in sorted(set(as_list(candidate.get("exclusive_locks"))) & set(as_list(active.get("exclusive_locks")))):
                    lock_conflicts.append({"type": "exclusive_lock_overlap", "active_task_id": active.get("task_id"), "lock": lock})

        if rules.get("write_write_conflict_blocks", True) and ww_conflicts:
            conflicts.extend(ww_conflicts)
            errors.append("write/write path conflict")
        else:
            conflicts.extend(ww_conflicts)

        if rules.get("exclusive_lock_conflict_blocks", True) and lock_conflicts:
            conflicts.extend(lock_conflicts)
            errors.append("exclusive lock conflict")
        else:
            conflicts.extend(lock_conflicts)

        if rules.get("write_read_conflict_warns", True) and wr_conflicts:
            warnings.append("write/read path overlap")
            conflicts.extend(wr_conflicts)

        if rules.get("same_repo_unspecified_scope_warns", True) and same_repo_unspecified:
            warnings.append("same repo with unspecified write scope")
            conflicts.extend({"type": "same_repo_unspecified_scope", **x} for x in same_repo_unspecified)

        if rules.get("unknown_scope_blocks_or_requires_operator", True) and unknown_scope:
            if decision.get("requires_operator_approval"):
                warnings.append("unknown candidate write scope requires operator approval")
            else:
                errors.append("unknown candidate write scope without operator approval")

        checks["write_write_conflict_absent"] = not ww_conflicts
        checks["exclusive_lock_conflict_absent"] = not lock_conflicts
        checks["unknown_scope_absent"] = not unknown_scope

        if decision.get("concurrency_allowed") is True and (ww_conflicts or lock_conflicts or (unknown_scope and not decision.get("requires_operator_approval"))):
            errors.append("decision allows concurrency despite blocking conflict")
        if errors and decision.get("requires_serial_execution") is False:
            warnings.append("blocking errors exist but decision does not require serial execution")

    if args.strict and warnings:
        errors.extend([f"strict_warning: {w}" for w in warnings])

    if errors:
        status = "BLOCK"
    elif warnings:
        status = "WARN"
    else:
        status = "PASS"

    out = {"status": status, "errors": errors, "warnings": warnings, "conflicts": conflicts, "checks": checks, "decision": decision}
    print(json.dumps(out, indent=2))
    sys.exit(1 if status == "BLOCK" else 0)


if __name__ == "__main__":
    main()
