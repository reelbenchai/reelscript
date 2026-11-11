#!/usr/bin/env python3
"""Read a public series directory from server-rendered JSON, without playback."""
import argparse
import json
from pathlib import Path
import re
import time
import urllib.parse
import urllib.request

HOSTS = {'hongguoduanju.com', 'www.hongguoduanju.com'}
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'

def series_id(value):
    if re.fullmatch(r'[0-9]{1,30}', value): return value
    url = urllib.parse.urlsplit(value)
    values = urllib.parse.parse_qs(url.query).get('series_id', [])
    if url.scheme != 'https' or url.hostname not in HOSTS or url.username or url.password or url.port not in (None,443) or url.path != '/detail' or len(values) != 1:
        raise ValueError('invalid_series_url')
    if not re.fullmatch(r'[0-9]{1,30}', values[0]): raise ValueError('invalid_series_id')
    return values[0]

class SameSiteRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if series_id(newurl) != series_id(req.full_url): raise ValueError('page_mismatch')
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def parse_catalog(html, sid):
    match = re.search(r'(?:window\.)?_ROUTER_DATA\s*=\s*', html)
    if not match: raise ValueError('router_data_unavailable')
    data, _ = json.JSONDecoder().raw_decode(html[match.end():])
    routes = data.get('loaderData', {})
    if not isinstance(routes, dict): raise ValueError('list_unavailable')
    series = next((v['seriesDetail'] for v in routes.values() if isinstance(v,dict)
                   and v.get('isSuccess') is not False and isinstance(v.get('seriesDetail'),dict)
                   and str(v['seriesDetail'].get('series_id')) == sid), None)
    if not series: raise ValueError('page_mismatch')
    ids = series.get('vid_list')
    if not isinstance(ids,list) or not ids or any(not re.fullmatch(r'[0-9]{1,30}',str(v)) for v in ids):
        raise ValueError('episode_directory_invalid')
    ids = [str(v) for v in ids]
    if len(set(ids)) != len(ids): raise ValueError('duplicate_episode_ids')
    def count(v): return v if isinstance(v,int) and not isinstance(v,bool) and v >= 0 else None
    total = count(series.get('episode_cnt'))
    return {'page_type':'list','platform':'hongguo','source_url':f'https://hongguoduanju.com/detail?series_id={sid}',
            'title':series.get('series_name') if isinstance(series.get('series_name'),str) else None,
            'item_count':len(ids),'items':[{'item_id':v,'title':None,'episode_number':i+1,
                'page_url':f'https://hongguoduanju.com/player/{sid}/{v}'} for i,v in enumerate(ids)],
            'has_more':None if total is None else total > len(ids),
            'metadata':{'source':'web','scope':'series_episodes','limit':None,'total_count':total,
                        'accessible_episode_count':count(series.get('accessible_episode_cnt')),'stop_reason':'loaded'}}

def collect(value, cache_dir=None):
    sid = series_id(value)
    cache = Path(cache_dir)/f'{sid}.json' if cache_dir else None
    if cache and cache.exists() and 0 <= time.time()-cache.stat().st_mtime < 3600:
        data=json.loads(cache.read_text(encoding='utf-8'))
        if data.get('source_url') == f'https://hongguoduanju.com/detail?series_id={sid}': return data
    url=f'https://hongguoduanju.com/detail?series_id={sid}'
    request=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'text/html','Referer':'https://hongguoduanju.com/'})
    with urllib.request.build_opener(SameSiteRedirect()).open(request,timeout=25) as response:
        raw=response.read(8*1024*1024+1)
        if len(raw)>8*1024*1024: raise ValueError('page_too_large')
        if series_id(response.url)!=sid: raise ValueError('page_mismatch')
        result=parse_catalog(raw.decode('utf-8'),sid)
    if cache:
        cache.parent.mkdir(parents=True,exist_ok=True)
        temporary=cache.with_suffix('.json.part')
        temporary.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        temporary.replace(cache)
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('--cache-dir')
    args=parser.parse_args()
    try: result=collect(args.source,args.cache_dir)
    except Exception as error:
        known={'invalid_series_url','invalid_series_id','page_mismatch','router_data_unavailable','list_unavailable','episode_directory_invalid','duplicate_episode_ids','page_too_large'}
        result={'error':{'code':str(error) if str(error) in known else 'list_unavailable','message':'The requested public series directory could not be verified.'}}
    print(json.dumps(result,ensure_ascii=False))
    return 1 if 'error' in result else 0

if __name__=='__main__': raise SystemExit(main())
