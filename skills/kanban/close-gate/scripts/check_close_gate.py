#!/usr/bin/env python3
"""Read-only close-gate checker for Kanban/GitHub issue workflows."""
import argparse,json,subprocess,sys
from pathlib import Path

def read_json(p):
    try: return json.loads(Path(p).read_text())
    except Exception as e: print(json.dumps({'passed':False,'error':f'bad json {p}: {e}'},indent=2)); sys.exit(2)
def git(args,cwd):
    try: return subprocess.run(['git']+args,cwd=cwd,text=True,capture_output=True,timeout=30)
    except Exception as e: return type('R',(),{'returncode':99,'stdout':'','stderr':str(e)})()
def unwrap_task(obj):
    """Return obj['task'] if present and dict, else obj. Handles Hermes {task:{...}} wrapper."""
    if isinstance(obj, dict) and 'task' in obj and isinstance(obj['task'], dict):
        return obj['task']
    return obj

def done(x):
    """Check done/archived status. Supports flat dict and Hermes {task:{...}} wrapper format.
    Flat takes priority: hermes kanban show (non-JSON flag) returns flat; --json may wrap."""
    x = x or {}
    # Flat: status at top level
    if x.get('status') in ('done', 'archived'):
        return True
    # Wrapper: status inside task sub-dict
    inner = x.get('task', {})
    if isinstance(inner, dict) and inner.get('status') in ('done', 'archived'):
        return True
    return False

def _as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if v is not None]
    return [str(value)]

def check_implementation_evidence(evidence):
    if isinstance(evidence, dict) and isinstance(evidence.get('implementation_persistence'), dict):
        ev = evidence['implementation_persistence']
    else:
        ev = evidence if isinstance(evidence, dict) else {}
    expected = _as_list(ev.get('expected_changed_paths') or ev.get('expected_write_paths'))
    actual = _as_list(ev.get('actual_changed_paths') or ev.get('actual_write_paths'))
    no_change_task = bool(ev.get('no_change_task') or ev.get('read_only_task'))
    worker_claimed_changes = bool(ev.get('worker_claimed_changes'))
    classification = ev.get('classification')
    expected_changes = bool(expected) or worker_claimed_changes
    missing = []
    warnings = []
    if classification == 'implementation_completed_but_no_persisted_changes':
        missing.append('implementation_completed_but_no_persisted_changes')
    if expected_changes and not actual and not no_change_task:
        missing.append('expected implementation changes have no persisted target repo evidence')
    if worker_claimed_changes and not actual:
        warnings.append('worker summary is not sufficient evidence without actual_changed_paths')
    if no_change_task and not actual:
        classification = classification or 'no_change_task_success'
    elif actual:
        classification = classification or 'implementation_success_with_persisted_changes'
    else:
        classification = classification or 'persistence_evidence_incomplete'
    return missing, warnings, {
        'classification': classification,
        'expected_changed_paths': expected,
        'actual_changed_paths': actual,
        'no_change_task': no_change_task,
        'worker_claimed_changes': worker_claimed_changes,
    }

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--adapter',required=True); p.add_argument('--issue-number'); p.add_argument('--parent-json',required=True); p.add_argument('--children-json',required=True)
    p.add_argument('--review-artifact',required=True); p.add_argument('--commit'); p.add_argument('--repo-path'); p.add_argument('--branch'); p.add_argument('--expected-files-json'); p.add_argument('--implementation-evidence'); p.add_argument('--wiki-path'); p.add_argument('--artifact-path'); p.add_argument('--output')
    a=p.parse_args(); adapter=read_json(a.adapter); parent=read_json(a.parent_json); children=read_json(a.children_json); missing=[]; warnings=[]
    if a.issue_number is None: warnings.append('issue existence not checked: no issue number provided')
    if not done(parent): missing.append('parent not done/archived')
    def child_id(c):
        inner = c.get('task', {})
        if isinstance(inner, dict): return inner.get('id') or c.get('id')
        return c.get('id')
    open_children=[child_id(c) for c in (children if isinstance(children,list) else children.get('children',[])) if not done(c)]
    if open_children: missing.append(f'children not done/archived: {open_children}')
    if not Path(a.review_artifact).is_file(): missing.append('review pass artifact missing')
    else:
        txt=Path(a.review_artifact).read_text(errors='ignore')
        if 'REVIEW_PASS' not in txt and '"review_outcome": "pass"' not in txt: missing.append('review pass marker missing')
    if a.commit:
        repo=a.repo_path or ((adapter.get('repo_path_by_host') or {}).get(adapter.get('source_host')))
        if repo and Path(repo).exists():
            if git(['cat-file','-e',a.commit+'^{commit}'],repo).returncode!=0: missing.append('commit does not exist locally')
            if a.branch and git(['branch','-r','--contains',a.commit],repo).stdout.find(a.branch)<0: missing.append('remote branch does not visibly contain commit')
        else: warnings.append('repo path unavailable locally; commit checks skipped')
    else: missing.append('commit hash missing')
    for label,path in [('wiki',a.wiki_path),('artifact',a.artifact_path)]:
        if path and not Path(path).exists(): missing.append(f'{label} path missing: {path}')
    implementation_persistence = None
    if a.implementation_evidence:
        ev_missing, ev_warnings, implementation_persistence = check_implementation_evidence(read_json(a.implementation_evidence))
        missing.extend(ev_missing)
        warnings.extend(ev_warnings)
    result={'passed':not missing,'missing_gates':missing,'warnings':warnings,'issue_number':a.issue_number,'commit':a.commit}
    if implementation_persistence is not None:
        result['implementation_persistence'] = implementation_persistence
    out=json.dumps(result,indent=2); print(out)
    if a.output: Path(a.output).write_text(out+'\n')
    sys.exit(0 if result['passed'] else 1)
if __name__=='__main__': main()
