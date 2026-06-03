#!/usr/bin/env python3
"""Check review evidence paths and outcome.
Exit codes: 0 pass, 1 gate failed, 2 usage/config error.
"""
import argparse,json,sys,re
from pathlib import Path

def load_json(path):
    try: return json.loads(Path(path).read_text())
    except Exception as e:
        print(json.dumps({"passed":False,"error":str(e)},indent=2)); sys.exit(2)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--adapter',required=True); p.add_argument('--artifact-json',required=True); p.add_argument('--report-txt',required=True); p.add_argument('--output-log',required=True)
    p.add_argument('--reviewer'); p.add_argument('--changed-files-json',help='JSON array of changed files'); p.add_argument('--browser-evidence'); p.add_argument('--output')
    a=p.parse_args(); adapter=load_json(a.adapter); missing=[]; warnings=[]
    for label,path in [('artifact_json',a.artifact_json),('report_txt',a.report_txt),('output_log',a.output_log)]:
        if not Path(path).is_file(): missing.append(f'{label} missing: {path}')
    text='\n'.join(Path(p).read_text(errors='ignore') if Path(p).exists() else '' for p in [a.artifact_json,a.report_txt,a.output_log])
    if 'REVIEW_PASS' not in text and 'REVIEW_FAIL' not in text: missing.append('explicit REVIEW_PASS or REVIEW_FAIL missing')
    expected=(adapter.get('workers') or {}).get('review')
    if a.reviewer and expected and a.reviewer != expected: missing.append(f'reviewer {a.reviewer} != adapter review worker {expected}')
    changed=[]
    if a.changed_files_json:
        try: changed=json.loads(Path(a.changed_files_json).read_text())
        except Exception as e: print(json.dumps({'passed':False,'error':f'bad changed files json: {e}'},indent=2)); sys.exit(2)
    ui_patterns=(adapter.get('verification') or {}).get('ui_file_detection_patterns') or [r'\.tsx$',r'\.ts$',r'\.jsx$',r'\.css$',r'\.scss$']
    ui_changed=any(any(re.search(pat,f) for pat in ui_patterns) for f in changed)
    browser=(adapter.get('verification') or {}).get('browser') or {}
    if (browser.get('required_if_ui') and ui_changed) or browser.get('always_required'):
        if not a.browser_evidence or not Path(a.browser_evidence).is_file(): missing.append('browser evidence required but missing')
    result={'passed':not missing,'missing_gates':missing,'warnings':warnings,'reviewer':a.reviewer,'expected_reviewer':expected,'ui_changed':ui_changed}
    out=json.dumps(result,indent=2); print(out)
    if a.output: Path(a.output).write_text(out+'\n')
    sys.exit(0 if result['passed'] else 1)
if __name__=='__main__': main()
