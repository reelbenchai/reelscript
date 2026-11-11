#!/usr/bin/env python3
"""Download an explicitly requested Hongguo batch; preserve incomplete episodes."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from hongguo_catalog import UA, HOSTS, series_id
from download_video import DownloadError, download, verify_mp4
from validate_result import validate_list, validate_result, resolve_video_path


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.part')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    os.replace(temporary, path)


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024*1024), b''):
            value.update(block)
    return value.hexdigest()


def count(value):
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    if isinstance(value, str) and re.fullmatch(r'[0-9]+', value):
        return int(value)
    return None


class WebsiteRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        url = urllib.parse.urlsplit(newurl)
        if url.scheme != 'https' or url.hostname not in HOSTS or url.username or url.password:
            raise DownloadError('page_mismatch', 'The website redirected outside its expected origin.')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def request(url, body=None, referer=None):
    headers = {'User-Agent': UA, 'Accept-Encoding': 'identity'}
    if body is not None:
        headers.update({'Content-Type':'application/json', 'Origin':'https://hongguoduanju.com'})
    if referer:
        headers['Referer'] = referer
    req = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(), headers=headers)
    try:
        with urllib.request.build_opener(WebsiteRedirect()).open(req, timeout=30) as response:
            raw = response.read(8*1024*1024+1)
            if len(raw) > 8*1024*1024:
                raise DownloadError('result_invalid', 'The website response exceeds the size limit.')
            return raw.decode('utf-8')
    except urllib.error.HTTPError as error:
        limited = False
        if error.code == 403:
            try:
                limited = json.loads(error.read(16384)).get('error') == 'public_fallback_unavailable'
            except (ValueError, AttributeError):
                pass
        raise DownloadError('web_access_limited' if limited else 'request_rejected',
                            'The selected episode is unavailable from this website source.') from None


def media_url(sid, eid):
    page = f'https://hongguoduanju.com/player/{sid}/{eid}'
    payload = json.loads(request('https://hongguoduanju.com/api/video/protected/fallback-play-info?aid=8662',
                                 {'item_id':eid}, page))
    if payload.get('base_resp', {}).get('StatusCode', 0) != 0:
        raise DownloadError('video_unavailable', 'The website did not return a playable source.')
    value = payload.get('main_url')
    parsed = urllib.parse.urlsplit(value) if isinstance(value, str) else None
    if not parsed or parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise DownloadError('video_unavailable', 'The website did not return a clear HTTPS media address.')
    return value


def detail(catalog, item):
    sid, eid = series_id(catalog['source_url']), item['item_id']
    html = request(item['page_url'])
    match = re.search(r'(?:window\.)?_ROUTER_DATA\s*=\s*', html)
    if not match:
        raise DownloadError('video_unavailable', 'The episode page contains no readable route data.')
    data, _ = json.JSONDecoder().raw_decode(html[match.end():])
    route = next((v for v in data.get('loaderData', {}).values()
                  if isinstance(v,dict) and str(v.get('series_id')) == sid
                  and str(v.get('vid')) == eid and v.get('isSuccess') is not False), None)
    if route is None:
        raise DownloadError('episode_mismatch', 'The page did not return the requested episode.')
    ids = [str(v) for v in route.get('seriesDetail', {}).get('vid_list', [])]
    if ids != [v['item_id'] for v in catalog['items']]:
        raise DownloadError('page_mismatch', 'The episode directory changed; refresh the catalog.')
    duration = (route.get('publicVideoSeo') or {}).get('durationSeconds')
    if isinstance(duration, bool) or not isinstance(duration, (int,float)) or not 0 < duration < 86400:
        duration = None
    social = route.get('episodeSocialInfo') or {}
    reviews = social.get('reviews') or {}
    rows = reviews.get('reviews') or []
    unique = {}
    for row in rows:
        if not isinstance(row,dict):
            continue
        text = str(row.get('content') or '').strip()
        likes = count(row.get('digg_count'))
        if text and likes is not None and likes > 100:
            key = str(row.get('review_id') or row.get('id') or text)
            unique[key] = {'content':text, 'like_count':likes}
    comments = sorted(unique.values(), key=lambda x:(-x['like_count'],x['content']))[:3]
    result = {
        'video_like_count':count(social.get('episode_like_count')),
        'comment_count':count(reviews.get('total_count')),
        'favorite_count':count((route.get('seriesSocialInfo') or {}).get('series_favorite_count')),
        'top_comments':comments,
        'episodes':[{'episode_number':x['episode_number'], 'episode_id':x['item_id'], 'page_url':x['page_url']}
                    for x in catalog['items']],
        'metadata':{'platform':'hongguo','series_id':sid,'episode_id':eid,
                    'video_like_count_scope':'episode','comment_count_scope':'episode',
                    'favorite_count_scope':'series','comment_scope':'web_preview','comments_examined':len(rows),
                    'comments_complete':reviews.get('has_more') in (False,0) or count(reviews.get('total_count')) == 0,
                    'ranking_scope':'collected_comments','comment_page_limit':5,'unavailable_fields':[]}}
    result['metadata']['unavailable_fields'] = [k for k in ('video_like_count','comment_count','favorite_count') if result[k] is None]
    return result, duration


def verify_saved(root, record, sid, eid):
    result_path = (root/record['json_path']).resolve()
    if not result_path.is_relative_to(root):
        raise ValueError('invalid result path')
    result = json.loads(result_path.read_text(encoding='utf-8'))
    validate_result(result, root)
    if result['metadata']['series_id'] != sid or result['metadata']['episode_id'] != eid:
        raise ValueError('saved identity mismatch')
    path = resolve_video_path(result['video_path'], root)
    if path.stat().st_size != record['size_bytes'] or digest(path) != record['sha256']:
        raise ValueError('saved file hash mismatch')
    verify_mp4(path, record['expected_duration'])


def decode_check(path):
    # Decode the whole file without rendering or saving any frames.
    result = subprocess.run(['ffmpeg','-v','error','-xerror','-nostdin','-i',str(path),
                             '-map','0:v:0','-map','0:a?','-f','null','-'],
                            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=300)
    if result.returncode:
        raise DownloadError('media_invalid', 'The downloaded episode failed a full media decode.')


def source_duration(url):
    """Probe the official clear source when non-first pages omit SEO duration."""
    try:
        probe = subprocess.run(['ffprobe','-v','error','-rw_timeout','15000000',
                                '-user_agent',UA,'-show_entries',
                                'format=duration:stream=codec_type,codec_name,codec_tag_string',
                                '-of','json',url],capture_output=True,text=True,timeout=30,check=True)
        info=json.loads(probe.stdout)
        duration=float(info['format']['duration'])
        streams=info.get('streams',[])
        if not 20 <= duration < 86400 or not any(s.get('codec_type')=='video' for s in streams):
            raise ValueError('preview or missing video')
        if any(s.get('codec_tag_string') in {'encv','enca'} for s in streams):
            raise ValueError('encrypted media')
        return duration
    except (OSError,subprocess.SubprocessError,ValueError,KeyError):
        raise DownloadError('duration_unavailable','The official media source could not be verified; previews are rejected.') from None


def summary(state):
    rows = [r for s in state['series'] for r in s['episodes']]
    done = sum(r['status']=='downloaded' for r in rows)
    counts = {key:sum(r['status']==key for r in rows) for key in sorted({r['status'] for r in rows})}
    return {'requested':len(rows),'downloaded':done,'remaining':len(rows)-done,
            'complete':done==len(rows),'counts':counts}


def run(args):
    root = args.root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    state_path = (root/args.state).resolve()
    if not state_path.is_relative_to(root) or state_path.suffix != '.json':
        raise ValueError('state path must be JSON inside the invocation root')
    for tool in ('ffprobe','ffmpeg'):
        if not shutil.which(tool):
            raise DownloadError('download_unavailable', f'{tool} is required for complete-media verification.')
    catalogs = {}
    for path in args.catalog:
        catalog = json.loads(path.read_text(encoding='utf-8'))
        validate_list(catalog)
        sid = series_id(catalog['source_url'])
        if catalog['platform'] != 'hongguo' or catalog['has_more'] is not False:
            raise ValueError('complete Hongguo catalogs are required')
        catalogs[sid] = catalog
    state_path.parent.mkdir(parents=True, exist_ok=True)
    lock = state_path.with_suffix('.lock')
    fd = os.open(lock, os.O_CREAT|os.O_EXCL|os.O_WRONLY, 0o600)
    os.write(fd,str(os.getpid()).encode())
    os.close(fd)
    try:
        state = json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {'version':1,'series':[]}
        if state['series'] and [s['series_id'] for s in state['series']] != list(catalogs):
            raise ValueError('resume catalogs differ from the saved batch')
        if not state['series']:
            for sid, catalog in catalogs.items():
                state['series'].append({'series_id':sid,'title':catalog['title'],'episodes':[
                    {'episode_id':item['item_id'],'episode_number':item['episode_number'],'status':'pending'}
                    for item in catalog['items']]})
        def checkpoint():
            state['summary'] = summary(state)
            save(state_path,state)
        checkpoint()
        new_count = 0
        for series in state['series']:
            sid = series['series_id']
            catalog = catalogs[sid]
            if [r['episode_id'] for r in series['episodes']] != [x['item_id'] for x in catalog['items']]:
                raise ValueError('resume episode IDs differ from the saved batch')
            limit = catalog['metadata']['accessible_episode_count']
            for item,record in zip(catalog['items'],series['episodes']):
                eid = item['item_id']
                if (root/'data/reeldown/batch.stop').exists():
                    checkpoint()
                    return state['summary']
                if record['status'] == 'downloaded':
                    try:
                        verify_saved(root, record, sid, eid)
                    except Exception:
                        record.update(status='verification_failed',error='saved_file_invalid')
                        checkpoint()
                    continue
                if args.max_new is not None and new_count >= args.max_new:
                    checkpoint()
                    return state['summary']
                if record['status'] == 'web_access_limited' and not args.retry_limited:
                    continue
                if record['status'] not in {'pending','web_access_limited'} and not args.retry_failed:
                    continue
                final = f'videos/hongguo/{sid}/{item["episode_number"]:03d}-{eid}.mp4'
                downloaded = None
                try:
                    # Confirm one boundary request; do not request every locked episode.
                    if limit is not None and item['episode_number'] > limit:
                        media_url(sid,eid)
                    data, duration = detail(catalog,item)
                    media = media_url(sid,eid)
                    duration_origin = 'website_metadata' if duration is not None else 'official_clear_media'
                    if duration is None:
                        duration = source_duration(media)
                    context = {'source':'hongguo_public_web','video_id':eid,
                               'headers':{'User-Agent':UA,'Referer':item['page_url']},'expected_duration':duration}
                    result_path = f'data/reeldown/hongguo/{eid}.json'
                    adopted = (root/final).exists()
                    if adopted:
                        try:
                            previous = json.loads((root/result_path).read_text(encoding='utf-8'))
                            validate_result(previous,root)
                            if (previous['metadata']['series_id'] != sid or previous['metadata']['episode_id'] != eid
                                    or previous['video_path'] != final):
                                raise ValueError('existing identity mismatch')
                            verify_mp4(root/final,duration)
                            decode_check(root/final)
                        except Exception:
                            raise DownloadError('existing_file_unverified','The existing file could not be reconciled; it was preserved.') from None
                        result={'video_path':final,**data}
                    else:
                        for attempt in range(2):
                            data['video_download_url'] = media if attempt == 0 else media_url(sid,eid)
                            try:
                                result = download(data,root,'hongguo',eid,final,context)
                                break
                            except DownloadError as error:
                                if error.code != 'download_url_expired' or attempt:
                                    raise
                        downloaded = resolve_video_path(result['video_path'],root)
                        decode_check(downloaded)
                    validate_result(result,root)
                    save(root/result_path,result)
                    record.update(status='downloaded',video_path=result['video_path'],json_path=result_path,
                                  size_bytes=(root/final).stat().st_size,sha256=digest(root/final),
                                  expected_duration=duration,duration_source=duration_origin,
                                  reused_existing=adopted,full_decode_verified=True)
                    record.pop('error',None)
                    new_count += 1
                    print(json.dumps({'series_id':sid,'episode_number':item['episode_number'],
                                      'status':'downloaded','size_bytes':record['size_bytes'],
                                      'duration_seconds':duration},ensure_ascii=True),flush=True)
                except DownloadError as error:
                    if downloaded is not None:
                        downloaded.unlink(missing_ok=True)
                    record.update(status='web_access_limited' if error.code=='web_access_limited' else 'failed',error=error.code)
                    if error.code == 'web_access_limited' and limit is not None and item['episode_number'] > limit:
                        series['website_boundary'] = {'episode_number':item['episode_number'],'response':'public_fallback_unavailable'}
                        for later in series['episodes'][item['episode_number']:]:
                            if later['status'] != 'downloaded':
                                later.update(status='web_access_limited',error='website_declared_limit',request_sent=False)
                    print(json.dumps({'series_id':sid,'episode_number':item['episode_number'],'error':error.code}),flush=True)
                    checkpoint()
                    if error.code == 'web_access_limited' and limit is not None and item['episode_number'] > limit:
                        break
                except Exception:
                    if downloaded is not None:
                        downloaded.unlink(missing_ok=True)
                    record.update(status='failed',error='download_failed')
                    print(json.dumps({'series_id':sid,'episode_number':item['episode_number'],'error':'download_failed'}),flush=True)
                checkpoint()
                time.sleep(1)
        checkpoint()
        return state['summary']
    finally:
        lock.unlink(missing_ok=True)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog',type=Path,nargs='+',required=True)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--state',default='data/reeldown/batch.json')
    parser.add_argument('--max-new',type=int)
    parser.add_argument('--retry-failed',action='store_true')
    parser.add_argument('--retry-limited',action='store_true')
    args=parser.parse_args()
    try:
        if args.max_new is not None and args.max_new < 1:
            raise ValueError('max-new must be positive')
        result=run(args)
        print(json.dumps(result),flush=True)
        return 0 if result['complete'] else 2
    except Exception as error:
        code=error.code if isinstance(error,DownloadError) else 'batch_invalid'
        print(json.dumps({'error':{'code':code,'message':'The batch stopped; existing files were preserved.'}}),flush=True)
        return 1


if __name__=='__main__':
    raise SystemExit(main())
