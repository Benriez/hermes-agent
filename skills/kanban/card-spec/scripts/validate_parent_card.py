#!/usr/bin/env python3
"""Validate a Kanban parent/card specification against a project adapter.

Read-only by default. Exit codes: 0 pass, 1 gate failed, 2 usage/config error.
"""
import argparse, json, sys
from pathlib import Path

WORKER_DEFAULTS={"implementation":"deep-implementer","review":"minimax-implementer"}
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

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--adapter', required=True, help='Project adapter JSON')
    p.add_argument('--card-json', required=True, help='Candidate/exported card JSON')
    p.add_argument('--output', help='Optional output JSON path')
    args=p.parse_args()
    adapter=load_json(args.adapter); raw_card=load_json(args.card_json)
    card=unwrap_task(raw_card)
    missing=[]; warnings=[]
    skills=get_skills(raw_card)
    if adapter.get('required_prism_context')=='superhermes' and card.get('assignee')=='superhermes': missing.append('superhermes must be metadata only, not assignee')
    if card.get('assignee') in FORBIDDEN_ASSIGNEES: missing.append(f"forbidden assignee: {card.get('assignee')}")
    workspace=str(card.get('workspace') or card.get('workdir') or '')
    source_host=adapter.get('source_host')
    repo_path=((adapter.get('repo_path_by_host') or {}).get(source_host) or '')
    if repo_path and workspace and workspace == repo_path: missing.append('parent workspace must not equal source repo path')
    if source_host in ('mac','windows') and repo_path and repo_path in workspace: missing.append('source-host repo path must be metadata only, not workspace')
    meta=json.dumps(card.get('metadata') or card.get('body') or {})
    if repo_path and repo_path not in meta: warnings.append('source repo path not observed in metadata/body; may be absent or encoded elsewhere')
    workers=adapter.get('workers') or {}
    if workers.get('implementation', WORKER_DEFAULTS['implementation']) != 'deep-implementer': warnings.append('implementation worker override differs from default deep-implementer')
    if workers.get('review', WORKER_DEFAULTS['review']) != 'minimax-implementer': warnings.append('review worker override differs from default minimax-implementer')
    if adapter.get('required_prism_context')=='superhermes' and card.get('required_prism_context') not in (None,'superhermes'):
        missing.append('required_prism_context must be superhermes or omitted for metadata-only context')
    result={'passed':not missing,'missing_gates':missing,'warnings':warnings,'adapter':adapter.get('project_id'),'card_id':get_field(raw_card,'id')}
    text=json.dumps(result,indent=2)
    if args.output: Path(args.output).write_text(text+'\n')
    print(text)
    sys.exit(0 if result['passed'] else 1)
if __name__=='__main__': main()
