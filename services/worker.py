"""Server-side adapters. Page completeness is mandatory; secrets never reach reports."""
import argparse,hashlib,json,math,os,time,urllib.parse,urllib.request,urllib.error,xml.etree.ElementTree as ET
from pathlib import Path
from .config import ROOT,DATA
from .store import Store,now
class ProviderError(Exception):
    def __init__(self,kind,code=''): self.kind=kind; self.code=str(code); super().__init__(kind)
def at_path(data,path):
    for part in path.split('.'):
        if not isinstance(data,dict): return None
        data=data.get(part)
    return data

def parse_response(raw,provider):
    try:
        if raw.lstrip().startswith(b'<'):
            root=ET.fromstring(raw)
            for el in root.iter(): el.tag=el.tag.split('}')[-1]
            def txt(tag):
                el=root.find('.//'+tag)
                return el.text if el is not None else None
            code=txt('resultCode') or txt('returnReasonCode')
            if code not in (None,'00','000','0'): raise ProviderError('quota' if code in ('22','23') else 'authentication' if code in ('20','30','31') else 'provider_error',code)
            count=txt('totalCount'); page=txt('pageNo')
            rows=[{el.tag:el.text for el in item} for item in root.findall('.//item')]
            if count is None: raise ProviderError('invalid_schema')
            return rows,int(count),int(page) if page else None
        body=json.loads(raw)
        if provider=='ME':
            r=body.get('response',body); h=r.get('header',{}); code=str(h.get('resultCode',r.get('resultCode','00')))
            if code not in ('00','000','0'): raise ProviderError('quota' if code in ('22','23') else 'authentication' if code in ('20','30','31') else 'provider_error',code)
            b=r.get('body',r); items=b.get('items',[]); rows=items.get('item',[]) if isinstance(items,dict) else items
            return [rows] if isinstance(rows,dict) else rows,int(b['totalCount']),int(b['pageNo']) if b.get('pageNo') else None
        rows=at_path(body,os.getenv('KEPCO_ITEMS_PATH','data')); count=at_path(body,os.getenv('KEPCO_TOTAL_PATH','totalCount'))
        if not isinstance(rows,list) or count is None: raise ProviderError('invalid_schema')
        return rows,int(count),None
    except ProviderError: raise
    except (ValueError,KeyError,TypeError,ET.ParseError): raise ProviderError('invalid_schema') from None

def fetch_pages(provider,url,key,extra=None,transport=None,sleeper=time.sleep,page_size=9999,audit=None):
    if not key: raise ProviderError('connection_pending')
    rows=[]; total=None; hashes=[]; raw_pages=[]
    for page in range(1,10001):
        params=dict(extra or {},pageNo=page,numOfRows=page_size)
        params['ServiceKey' if provider=='ME' else os.getenv('KEPCO_KEY_PARAM','apiKey')]=urllib.parse.unquote(key)
        target=url+'?'+urllib.parse.urlencode(params)
        raw=None
        for attempt in range(3):
            try:
                if transport: raw=transport(target)
                else:
                    with urllib.request.urlopen(target,timeout=25) as resp: raw=resp.read()
                if audit: audit(dict(page=page,attempt=attempt+1,sha256=hashlib.sha256(raw).hexdigest(),status='received'),raw)
                items,count,returned_page=parse_response(raw,provider)
                break
            except urllib.error.HTTPError as e:
                if e.code in (401,403): raise ProviderError('authentication',e.code) from None
                if e.code==429: raise ProviderError('quota',e.code) from None
                if attempt==2: raise ProviderError('http_error',e.code) from None
            except ProviderError as e:
                if e.kind in ('authentication','quota','invalid_schema') or attempt==2: raise
            except (OSError,TimeoutError):
                if attempt==2: raise ProviderError('network_error') from None
            if audit: audit(dict(page=page,attempt=attempt+1,status='retry'),None)
            sleeper(2**attempt)
        if returned_page is not None and returned_page!=page: raise ProviderError('page_mismatch')
        if total is not None and count!=total: raise ProviderError('unstable_total')
        total=count
        digest=hashlib.sha256(raw).hexdigest()
        if digest in hashes and items: raise ProviderError('repeated_page')
        hashes.append(digest); raw_pages.append(raw)
        if not items and len(rows)<total: raise ProviderError('missing_page')
        rows.extend(items)
        if len(rows)==total: return rows,hashes,raw_pages
        if len(rows)>total: raise ProviderError('count_mismatch')
    raise ProviderError('page_limit')

def number(v):
    try:
        f=float(v); return f if math.isfinite(f) else None
    except (ValueError,TypeError): return None

def normalize_me(rows,stamp):
    stations={}; mapping=json.loads(os.getenv('ME_STATUS_MAP','{}')); fast_types=json.loads(os.getenv('ME_FAST_TYPES','[]')); verified=os.getenv('ME_MAPPING_VERIFIED')=='true'; duplicates=set(); seen=set()
    for r in rows:
        sid=r.get('statId'); cid=r.get('chgerId')
        if not sid or not cid: raise ProviderError('missing_identifier')
        key=f'ME:{sid}:{cid}'
        if key in seen: raise ProviderError('duplicate_equipment')
        seen.add(key)
        s=stations.setdefault(sid,dict(id=f'ME:{sid}',name=r.get('statNm',sid),address=r.get('addr',''),district=next((v for v in (r.get('addr') or '').split() if v.endswith('구')),'미확인'),lat=number(r.get('lat')),lon=number(r.get('lng')),annual_kwh=None,monthly_kwh=None,match_status='unmatched',chargers=[],quality_flags=[]))
        status=mapping.get(str(r.get('stat')),'UNKNOWN') if verified else 'UNKNOWN'
        current_verified=os.getenv('ME_INVENTORY_CURRENT_STATUS_VERIFIED')=='true'
        s['chargers'].append(dict(id=key,source_station_id=sid,source_charger_id=cid,power_kw=number(r.get('output')),status=status,source_status_raw=r.get('stat'),source_updated_at=r.get('statUpdDt'),last_verified_at=stamp if verified and current_verified else None,ttl_minutes=int(os.getenv('STATE_TTL_MINUTES','15')),fast_verified=verified and str(r.get('chgerType')) in fast_types,physical_verified=False,sharing_verified=False,access_verified=False,compatible_verified=False,deleted=r.get('delYn')=='Y',source_fields=r))
    return list(stations.values())

def collect_once(service=None):
    from backend.app.core import ExternalService
    service = service or ExternalService()
    service.refresh()
    result = service.status()
    print(json.dumps(result, ensure_ascii=False))
    return result


def cross_validate(primary,secondary,links,field_map,status_map):
    out=[]
    for c in primary:
        link=links.get(c['id'])
        other=next((r for r in secondary if str(r.get(field_map.get('id',''))) == str(link)),None) if link else None
        reason='매칭 불가'; comparison=None
        if other:
            try:
                a=datetime.fromisoformat(c['source_updated_at']); b=datetime.fromisoformat(other[field_map['updated_at']])
                if abs((a-b).total_seconds())>300: reason='시간차로 비교 불가'
                else: comparison=status_map.get(str(other.get(field_map['status']))); reason='일치' if comparison==c['status'] else '불일치'
            except (ValueError,KeyError,TypeError): reason='시간차로 비교 불가'
        out.append(dict(charger_id=c['id'],result=reason,primary_status=c['status'],secondary_status=comparison))
    return out
from datetime import datetime
if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--loop',action='store_true'); args=p.parse_args()
    while True:
        collect_once()
        if not args.loop: break
        time.sleep(max(60,int(os.getenv('COLLECT_INTERVAL_SECONDS','600'))))
