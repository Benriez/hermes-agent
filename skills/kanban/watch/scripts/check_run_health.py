#!/usr/bin/env python3
"""Read-only Kanban run/card health and implementation persistence checker."""
import argparse, json, os, sys, time, re
from pathlib import Path

FORBIDDEN_PROVIDERS = ['qwopus', 'llama-swap', 'local-implementer', 'local-reviewer']
FORBIDDEN_ASSIGNEES = {'superhermes', 'local-implementer', 'local-reviewer'}


def read_json(p):
    try:
        return json.loads(Path(p).read_text())
    except Exception as e:
        print(json.dumps({'passed': False, 'error': f'bad json {p}: {e}'}, indent=2))
        sys.exit(2)


def pid_alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except Exception:
        return False


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


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if v is not None]
    return [str(value)]


def check_persistence(evidence):
    """Return (missing, warnings, detail) for implementation persistence evidence.

    Expected shape is intentionally small and universal:
    {
      "implementation_persistence": {
        "implementation_completed": true,
        "worker_claimed_changes": true,
        "no_change_task": false,
        "expected_changed_paths": ["path"],
        "actual_changed_paths": [],
        "classification": "implementation_completed_but_no_persisted_changes"
      }
    }
    """
    if isinstance(evidence, dict) and isinstance(evidence.get('implementation_persistence'), dict):
        ev = evidence['implementation_persistence']
    else:
        ev = evidence if isinstance(evidence, dict) else {}

    missing = []
    warnings = []
    expected = _as_list(ev.get('expected_changed_paths') or ev.get('expected_write_paths'))
    actual = _as_list(ev.get('actual_changed_paths') or ev.get('actual_write_paths'))
    no_change_task = bool(ev.get('no_change_task') or ev.get('read_only_task'))
    implementation_completed = bool(ev.get('implementation_completed', True))
    worker_claimed_changes = bool(ev.get('worker_claimed_changes'))
    classification = ev.get('classification')

    expected_changes = bool(expected) or worker_claimed_changes

    if implementation_completed and expected_changes and not actual and not no_change_task:
        missing.append('implementation_completed_but_no_persisted_changes')
        classification = classification or 'implementation_completed_but_no_persisted_changes'

    if worker_claimed_changes and not actual:
        warnings.append('worker summary is not sufficient evidence without actual_changed_paths')

    if not expected_changes and not no_change_task:
        warnings.append('no expected_changed_paths provided; persistence check is informational only')

    if no_change_task and actual:
        warnings.append('no_change_task is true but actual_changed_paths is non-empty')

    if not classification:
        if missing:
            classification = 'implementation_completed_but_no_persisted_changes'
        elif no_change_task and not actual:
            classification = 'no_change_task_success'
        elif actual:
            classification = 'implementation_success_with_persisted_changes'
        else:
            classification = 'persistence_evidence_incomplete'

    detail = {
        'classification': classification,
        'implementation_completed': implementation_completed,
        'worker_claimed_changes': worker_claimed_changes,
        'no_change_task': no_change_task,
        'expected_changed_paths': expected,
        'actual_changed_paths': actual,
        'expected_change_count': len(expected),
        'actual_change_count': len(actual),
        'passed': not missing,
    }
    return missing, warnings, detail


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--adapter', required=True)
    p.add_argument('--card-json', required=True)
    p.add_argument('--events-json')
    p.add_argument('--log-file')
    p.add_argument('--stale-seconds', type=int, default=900)
    p.add_argument('--persistence-json', help='Optional implementation persistence evidence JSON')
    p.add_argument('--output')
    a = p.parse_args()

    adapter = read_json(a.adapter)
    raw_card = read_json(a.card_json)
    card = unwrap_task(raw_card)
    missing = []
    warnings = []
    persistence_detail = None

    assignee = card.get('assignee')
    if assignee in FORBIDDEN_ASSIGNEES:
        missing.append(f'forbidden assignee: {assignee}')

    expected = [
        (adapter.get('workers') or {}).get('implementation'),
        (adapter.get('workers') or {}).get('review'),
    ]
    if assignee and assignee not in expected and card.get('status') in ('ready', 'running', 'review'):
        warnings.append(f'assignee {assignee} not one of adapter workers {expected}')

    workspace = str(card.get('workspace') or card.get('workdir') or '')
    repo = ((adapter.get('repo_path_by_host') or {}).get(adapter.get('source_host')) or '')
    if repo and workspace.startswith(repo):
        missing.append('wrong workspace spawn: source repo path used as workspace')

    pid = card.get('worker_pid') or card.get('pid')
    if pid and not pid_alive(pid):
        missing.append(f'dead pid: {pid}')

    hb = card.get('last_heartbeat') or card.get('heartbeat_at')
    if hb:
        try:
            if time.time() - float(hb) > a.stale_seconds:
                missing.append('stale heartbeat')
        except Exception:
            warnings.append('heartbeat not numeric epoch')

    logtext = ''
    if a.log_file and Path(a.log_file).exists():
        logtext = Path(a.log_file).read_text(errors='ignore')
    for token in FORBIDDEN_PROVIDERS:
        if re.search(re.escape(token), logtext, re.I):
            missing.append(f'forbidden provider/profile mention in logs: {token}')

    if a.persistence_json:
        evidence = read_json(a.persistence_json)
        p_missing, p_warnings, persistence_detail = check_persistence(evidence)
        missing.extend(p_missing)
        warnings.extend(p_warnings)

    result = {
        'passed': not missing,
        'missing_gates': missing,
        'warnings': warnings,
        'card_id': get_field(raw_card, 'id'),
    }
    if persistence_detail is not None:
        result['implementation_persistence'] = persistence_detail

    out = json.dumps(result, indent=2)
    print(out)
    if a.output:
        Path(a.output).write_text(out + '\n')
    sys.exit(0 if result['passed'] else 1)


if __name__ == '__main__':
    main()
