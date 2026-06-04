#!/usr/bin/env python3
"""Validate a Kanban parent/card specification against a project adapter.

Read-only. Exit codes: 0 pass, 1 gate failed, 2 usage/config error.
Worker names are validated against the adapter's declared workers only.
No universal worker defaults are assumed.
"""
import argparse, json, sys
from pathlib import Path

FORBIDDEN_ASSIGNEES={"superhermes","local-implementer","local-reviewer"}

def load_json(path):
    try: return json.loads(Path(path).read_text())
    except Exception as e:
        print(json.dumps({"passed":False,"error":f"cannot read json {path}: {e}"},indent=2)); sys.exit(2)

def unwrap_task(obj):
    """Return obj['task'] if present and dict, else obj. Handles Hermes {task:{...}} wrapper."""
    if isinstance(obj, dict) and 'task' in obj and isinstance(obj['task'], dict):
        return obj['task']
    return obj

def get_field(obj, key, default=None):
    """Get field from normalized card (unwrapped task first, then top-level fallback)."""
    if isinstance(obj, dict):
        inner = obj.get('task', {})
        if isinstance(inner, dict) and key in inner:
            return inner[key]
        return obj.get(key, default)
    return default

def get_skills(card):
    """Resolve skills from card. Checks required_skills or skills; handles null/string/list."""
    raw = None
    for key in ('required_skills', 'skills'):
        raw = get_field(card, key)
        if raw is not None:
            break
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        return [raw] if raw else []
    return []

def validate_runtime_skills(skills, forbidden=None):
    """Check that runtime skills contain only worker-loadable skills.
    
    Workflow/operator skills (kanban-card-spec, kanban-watch, kanban-review,
    kanban-close-gate) are NOT runtime skills — they belong in body metadata.
    Only prism-full (or other worker-loadable analysis skills) belong in
    the card.skills field / required_skills.
    
    Returns list of violations (empty = pass).
    """
    OPERATOR_SKILLS={"kanban-card-spec","kanban-watch","kanban-review","kanban-close-gate"}
    violations=[]
    for s in skills:
        if s in OPERATOR_SKILLS:
            violations.append(f"operator skill '{s}' belongs in body metadata, not card.skills/runtime skills")
    return violations

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--adapter', required=True, help='Project adapter JSON')
    p.add_argument('--card-json', required=True, help='Candidate/exported card JSON')
    p.add_argument('--output', help='Optional output JSON path')
    args=p.parse_args()
    adapter=load_json(args.adapter)
    raw_card=load_json(args.card_json)
    card=unwrap_task(raw_card)
    missing=[]; warnings=[]

    # Forbidden assignee check (universal — applies even without adapter workers)
    assignee=card.get('assignee')
    if assignee in FORBIDDEN_ASSIGNEES:
        missing.append(f"forbidden assignee: {assignee}")

    # Prism context check
    if adapter.get('required_prism_context')=='superhermes' and card.get('assignee')=='superhermes':
        missing.append('superhermes must be metadata only, not assignee')
    if adapter.get('required_prism_context')=='superhermes' and card.get('required_prism_context') not in (None,'superhermes'):
        missing.append('required_prism_context must be superhermes or omitted for metadata-only context')

    # Workspace / repo path check (universal)
    workspace=str(card.get('workspace') or card.get('workdir') or '')
    source_host=adapter.get('source_host')
    repo_path=((adapter.get('repo_path_by_host') or {}).get(source_host) or '')
    if repo_path and workspace and workspace==repo_path:
        missing.append('parent workspace must not equal source repo path')
    if source_host in ('mac','windows') and repo_path and repo_path in workspace:
        missing.append('source-host repo path must be metadata only, not workspace')
    meta=json.dumps(card.get('metadata') or card.get('body') or {})
    if repo_path and repo_path not in meta:
        warnings.append('source repo path not observed in metadata/body; may be absent or encoded elsewhere')

    # Runtime skill check (universal — operator skills belong in body metadata)
    skills=get_skills(raw_card)
    skill_violations=validate_runtime_skills(skills)
    missing.extend(skill_violations)
    if skill_violations:
        warnings.append(f"runtime skill check: {len(skill_violations)} violation(s) — operator skills in card.skills field")

    # Worker validation: adapter-driven only (no universal defaults)
    # Concrete worker names belong to the project adapter, not the universal script.
    workers=adapter.get('workers') or {}
    concrete_worker_validation="skipped_no_adapter"
    if workers:
        concrete_worker_validation="adapter-driven"
        # Adapter declares expected workers — check card assignee against declared workers.
        # Do NOT warn if assignee differs from some universal default (there is no universal default).
        # Warn only if card assignee is set to a forbidden value that somehow passed earlier checks.
        # The primary worker-name check is: does the declared adapter have workers?
        # Since we have workers, we validate card assignee is one of them (if set).
        expected=set(workers.values())
        if assignee and assignee not in FORBIDDEN_ASSIGNEES and assignee not in expected:
            warnings.append(f"assignee '{assignee}' not in adapter declared workers: {list(expected)}")
    else:
        concrete_worker_validation="skipped_no_adapter"
        warnings.append('adapter does not declare workers; concrete worker name validation skipped')

    result={
        'passed':not missing,
        'missing_gates':missing,
        'warnings':warnings,
        'adapter':adapter.get('project_id'),
        'card_id':get_field(raw_card,'id'),
        'concrete_worker_validation':concrete_worker_validation,
        'card_assignee':assignee,
        'adapter_declared_workers':workers or None,
        'runtime_skills_check':'operator_skills_forbidden_in_card_skills'
    }
    text=json.dumps(result,indent=2)
    if args.output: Path(args.output).write_text(text+'\n')
    print(text)
    sys.exit(0 if result['passed'] else 1)

if __name__=='__main__': main()
