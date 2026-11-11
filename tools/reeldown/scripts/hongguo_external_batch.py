#!/usr/bin/env python3
"""Resume a cataloged batch with a reviewed external downloader on its destination."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parent))
import hongguo_batch as batch
from download_video import verify_mp4
from validate_result import validate_result,resolve_video_path
from backend_session import BackendSession


def metadata(series,record,root):
    favorite=None
    # A previously verified first-episode result may supply the series-wide count.
    first=series['episodes'][0]
    if first.get('status')=='downloaded' and first.get('json_path'):
        try:
            prior=json.loads((root/first['json_path']).read_text(encoding='utf-8'))
            if prior['metadata']['series_id']==series['series_id']:
                favorite=batch.count(prior['favorite_count'])
        except (OSError,ValueError,KeyError):
            pass
    sid=series['series_id']
    return {'video_like_count':None,'comment_count':None,'favorite_count':favorite,'top_comments':[],
      'episodes':[{'episode_number':r['episode_number'],'episode_id':r['episode_id'],
                   'page_url':f'https://hongguoduanju.com/player/{sid}/{r["episode_id"]}'} for r in series['episodes']],
      'metadata':{'platform':'hongguo','series_id':sid,'episode_id':record['episode_id'],
       'video_like_count_scope':'episode','comment_count_scope':'episode','favorite_count_scope':'series',
       'comment_scope':'unavailable','comments_examined':0,'comments_complete':False,
       'ranking_scope':'collected_comments','comment_page_limit':5,
       'unavailable_fields':['video_like_count','comment_count']+(['favorite_count'] if favorite is None else [])}}


def verify_report(report,eid,path):
    if not isinstance(report,dict) or report.get('success') is not True or report.get('episode_id')!=eid:
        raise ValueError('external_identity_mismatch')
    duration=report.get('expected_duration')
    if isinstance(duration,bool) or not isinstance(duration,(float,int)) or not 0<duration<86400:
        raise ValueError('external_duration_invalid')
    if path.stat().st_size!=report.get('bytes') or batch.digest(path)!=report.get('sha256'):
        raise ValueError('external_hash_mismatch')
    verify_mp4(path,duration)
    if report.get('full_decode_verified') is not True:
        batch.decode_check(path)


def run(args):
    root=args.root.resolve()
    state_path=(root/args.state).resolve()
    if not state_path.is_relative_to(root):raise ValueError('invalid_state_path')
    state=json.loads(state_path.read_text(encoding='utf-8'))
    state.pop('source_stop_reason',None)
    # This file is caller-supplied trusted configuration, never platform content.
    config=json.loads(args.backend.read_text(encoding='utf-8'))
    command=config.get('command')
    if not isinstance(command,list) or not command or any(not isinstance(s,str) for s in command):
        raise ValueError('invalid_backend_command')
    protocol=config.get('protocol','oneshot')
    if protocol not in {'oneshot','jsonl'}:raise ValueError('invalid_backend_protocol')
    if protocol=='oneshot' and (not any('{episode_id}' in s for s in command) or not any('{output}' in s for s in command)):
        raise ValueError('backend_requires_identity_and_destination')
    session=BackendSession(command) if protocol=='jsonl' else None
    for s in state['series']:
        if not isinstance(s['series_id'],str) or not s['series_id'].isascii() or not s['series_id'].isdigit():
            raise ValueError('invalid_series_id')
        seen=set()
        for i,r in enumerate(s['episodes']):
            eid=r['episode_id']
            if not isinstance(eid,str) or not eid.isascii() or not eid.isdigit() or eid in seen or r['episode_number']!=i+1:
                raise ValueError('invalid_episode_directory')
            seen.add(eid)
    lock=state_path.with_suffix('.lock')
    fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    os.write(fd,str(os.getpid()).encode());os.close(fd)
    def checkpoint():
        state['summary']=batch.summary(state)
        batch.save(state_path,state)
    processed=0
    attempted=0
    max_attempts=getattr(args,'max_attempts',None)
    failures=0
    try:
        for series in state['series']:
            sid=series['series_id']
            for record in series['episodes']:
                if (root/'data/reeldown/batch.stop').exists():
                    checkpoint();return state['summary']
                eid=record['episode_id']
                if record['status']=='downloaded':
                    batch.verify_saved(root,record,sid,eid)
                    continue
                if args.max_new and processed>=args.max_new:
                    checkpoint();return state['summary']
                relative=f'videos/hongguo/{sid}/{record["episode_number"]:03d}-{eid}.mp4'
                destination=resolve_video_path(relative,root)
                receipt=Path(str(destination)+'.verification.json')
                try:
                    existed=destination.exists()
                    if existed:
                        if not receipt.is_file():raise ValueError('existing_file_unverified')
                        report=json.loads(receipt.read_text(encoding='utf-8'))
                    else:
                        if max_attempts is not None and attempted>=max_attempts:
                            state['source_stop_reason']='backend_attempt_limit'
                            checkpoint();return state['summary']
                        attempted+=1
                        if session:
                            report=session.request(eid,destination)
                            returncode=0
                        else:
                            argv=[part.replace('{episode_id}',eid).replace('{output}',str(destination)) for part in command]
                            result=subprocess.run(argv,stdin=subprocess.DEVNULL,capture_output=True,text=True,
                                                  encoding='utf-8',timeout=900,check=False)
                            lines=result.stdout.strip().splitlines()
                            report=json.loads(lines[-1]) if lines else {}
                            returncode=result.returncode
                        if returncode or report.get('success') is not True:
                            code=report.get('error')
                            raise ValueError(code if isinstance(code,str) and code.replace('_','').isalnum() else 'external_download_failed')
                    verify_report(report,eid,destination)
                    public={'video_path':relative,**metadata(series,record,root)}
                    validate_result(public,root)
                    result_path=f'data/reeldown/hongguo/{eid}.json'
                    batch.save(root/result_path,public)
                    record.update(status='downloaded',video_path=relative,json_path=result_path,
                     size_bytes=report['bytes'],sha256=report['sha256'],expected_duration=report['expected_duration'],
                     duration_source='external_selected_episode_model',source='external_downloader',
                     full_decode_verified=True,reused_existing=False,recovered_receipt=existed)
                    for key in ('codec','width','height','quality'):
                        if key in report:record[key]=report[key]
                    if report.get('source_kind')=='registered_client':
                        record['source_kind']='registered_client'
                    record.pop('error',None);record.pop('request_sent',None)
                    failures=0;processed+=1
                    checkpoint()
                    receipt.unlink(missing_ok=True)
                    print(json.dumps({'series_id':sid,'episode_number':record['episode_number'],
                                      'status':'downloaded','downloaded_total':state['summary']['downloaded']}),flush=True)
                except Exception as error:
                    code=str(error) if isinstance(error,ValueError) and len(str(error))<80 and str(error).replace('_','').isalnum() else 'external_download_failed'
                    record.update(status='failed',error=code)
                    failures+=1
                    checkpoint()
                    print(json.dumps({'series_id':sid,'episode_number':record['episode_number'],'error':code}),flush=True)
                    if failures>=3:
                        state['source_stop_reason']='three_consecutive_external_failures'
                        checkpoint();return state['summary']
                time.sleep(1)
        checkpoint();return state['summary']
    finally:
        try:
            if session:session.close()
        finally:
            lock.unlink(missing_ok=True)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--state',default='data/reeldown/batch.json')
    p.add_argument('--backend',type=Path,required=True)
    p.add_argument('--max-new',type=int)
    p.add_argument('--max-attempts',type=int,
                   help='Maximum external download requests, including failures; receipt recovery does not count.')
    args=p.parse_args()
    try:
        if args.max_new is not None and args.max_new<1:raise ValueError('invalid_limit')
        if args.max_attempts is not None and args.max_attempts<1:raise ValueError('invalid_attempt_limit')
        result=run(args)
        print(json.dumps(result),flush=True)
        return 0 if result['complete'] else 2
    except Exception as error:
        # Report only the type, never backend commands, URLs, or credentials.
        print(json.dumps({'error':{'code':'external_batch_stopped','error_type':type(error).__name__,
                                  'message':'Existing files were preserved; inspect the public manifest.'}}),flush=True)
        return 1


if __name__=='__main__':raise SystemExit(main())
