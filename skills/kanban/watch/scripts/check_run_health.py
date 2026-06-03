#!/usr/bin/env python3
"""Read-only Kanban run/card health checker."""
import argparse,json,os,sys,time,re
from pathlib import Path
FORBIDDEN_PROVIDERS=['qwopus','llama-swap','local-implementer','local-reviewer']
FORBIDDEN_ASSIGNEES={'superhermes','local-implementer','local-reviewer'}
def read_json(p):
    try: return json.loads(Path(p).read_text())
    except Exception as e: print(json.dumps({'passed':False,'error':f'bad json {p}: {e}'},indent=2)); sys.exit(2)
def pid_alive(pid):
    try: os.kill(int(pid),0); return True
    except Exception: return False
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

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--adapter',required=True); p.add_argument('--card-json',required=True); p.add_argument('--events-json'); p.add_argument('--log-file'); p.add_argument('--stale-seconds',type=int,default=900); p.add_argument('--output')
    a=p.parse_args(); adapter=read_json(a.adapter); raw_card=read_json(a.card_json); card=unwrap_task(raw_card); missing=[]; warnings=[]
    assignee=card.get('assignee')
    if assignee in FORBIDDEN_ASSIGNEES: missing.append(f'forbidden assignee: {assignee}')
    expected=[(adapter.get('workers') or {}).get('implementation'),(adapter.get('workers') or {}).get('review')]
    if assignee and assignee not in expected and card.get('status') in ('ready','running','review'): warnings.append(f'assignee {assignee} not one of adapter workers {expected}')
    workspace=str(card.get('workspace') or card.get('workdir') or '')
    repo=((adapter.get('repo_path_by_host') or {}).get(adapter.get('source_host')) or '')
    if repo and workspace.startswith(repo): missing.append('wrong workspace spawn: source repo path used as workspace')
    pid=card.get('worker_pid') or card.get('pid')
    if pid and not pid_alive(pid): missing.append(f'dead pid: {pid}')
    hb=card.get('last_heartbeat') or card.get('heartbeat_at')
    if hb:
        try:
            if time.time()-float(hb)>a.stale_seconds: missing.append('stale heartbeat')
        except Exception: warnings.append('heartbeat not numeric epoch')
    logtext=''
    if a.log_file and Path(a.log_file).exists(): logtext=Path(a.log_file).read_text(errors='ignore')
    for token in FORBIDDEN_PROVIDERS:
        if re.search(re.escape(token),logtext,re.I): missing.append(f'forbidden provider/profile mention in logs: {token}')
    result={'passed':not missing,'missing_gates':missing,'warnings':warnings,'card_id':get_field(raw_card,'id')}
    out=json.dumps(result,indent=2); print(out)
    if a.output: Path(a.output).write_text(out+'\n')
    sys.exit(0 if result['passed'] else 1)
if __name__=='__main__': main()
