import copy,gzip,hashlib,hmac,json,os,re
from datetime import datetime,timedelta
from difflib import SequenceMatcher
from .config import DATA
from .store import Store,now
from .sample import sample_snapshot
from .engine import analyze,simulate,alternatives,maintenance,KST,fresh,FORMULA_VERSION,session_hourly
from .worker import cross_validate
class ApiError(Exception):
    def __init__(self,status,message): self.status=status; self.message=message
class Service:
    def __init__(self,store=None,external=None,analysis=None): self.store=store or Store(); self.sample=sample_snapshot(); self.sessions=None; self.external=external; self.analysis=analysis
    def jsonfile(self,name,default):
        p=DATA/name
        return json.loads(p.read_text(encoding='utf-8')) if p.exists() else default
    def radius(self,q):
        try: value=int(q.get('radius_m','500'))
        except (ValueError,TypeError): raise ApiError(422,'반경은 500 또는 1000m입니다.')
        if value not in (500,1000): raise ApiError(422,'반경은 500 또는 1000m입니다.')
        return value
    def snapshot(self,mode,radius=500):
        if mode=='sample': return copy.deepcopy(self.sample)
        if mode!='live': raise ApiError(422,'mode는 live 또는 sample입니다.')
        if self.analysis is not None:return self.analysis.legacy_snapshot(radius)
        source=self.external.legacy_snapshot() if self.external else self.store.latest('snapshots')
        if not source: raise ApiError(503,'실관측 연결 대기 · 환경공단 수집을 먼저 실행하세요.')
        s=copy.deepcopy(source); demand=self.jsonfile('demand.json',{}); matches=self.store.all('matches'); version=hashlib.sha256(json.dumps(matches,sort_keys=True).encode()).hexdigest()[:12]
        source_names_normalized={re.sub(r'\s+','',n) for n in demand}
        for station in s['stations']:
            m=next((m for m in matches if m.get('station_id')==station['id']),None)
            station['analysis_target']=bool(m and not m.get('external_network')) or re.sub(r'\s+','',station['name']) in source_names_normalized
            if m:
                station.update(match_status='network_only' if m.get('external_network') else m['status'],source_name=m.get('source_name'),fast_only_history_verified=m.get('fast_only_history_verified',False),covered_days=m.get('covered_days'))
                d=demand.get(m.get('source_name'))
                if d: station.update(annual_kwh=d['annual_kwh'],monthly_kwh=[v if i+1 in d['months'] else None for i,v in enumerate(d['monthly_kwh'])])
                for c in station['chargers']:
                    c.update({k:m.get(k,False) for k in ('physical_verified','sharing_verified','access_verified','compatible_verified')})
                    if m.get('physical_unit_ids',{}).get(c['id']): c['physical_unit_id']=m['physical_unit_ids'][c['id']]
        s['id']=source['id']+'-'+version; s['mapping_version']=version
        return s
    def run(self,q):
        mode=q.get('mode','live'); radius=self.radius(q); requested=q.get('analysis_run_id')
        if requested:
            run=self.store.get('runs',requested)
            if not run: raise ApiError(404,'분석 실행을 찾을 수 없습니다.')
            if run.get('formula_version')!=FORMULA_VERSION: raise ApiError(409,'영향도 공식이 변경되었습니다. 새 분석을 실행하세요.')
            if run['snapshot']['mode']!=mode or run['radius_m']!=radius: raise ApiError(409,'기준 실행의 모드·반경과 요청이 다릅니다.')
            return run
        s=self.snapshot(mode,radius); at=now(); r=analyze(s,radius,at)
        rid=hashlib.sha256(f"{FORMULA_VERSION}:{s['id']}:{radius}:{at[:16]}".encode()).hexdigest()[:24]
        run=self.store.get('runs',rid)
        if run: return run
        run=dict(id=rid,formula_version=FORMULA_VERSION,snapshot=s,radius_m=radius,q95=r['q95'],evaluated_at=at)
        self.store.put('runs',run,rid); return run
    def meta(self,run):
        s=run['snapshot']
        return dict(snapshot_id=s['id'],analysis_run_id=run['id'],observed_at=s['observed_at'],evaluated_at=run['evaluated_at'],demand_period=['2025-01-01','2025-12-31'],formula_version=FORMULA_VERSION,quality_flags=s.get('quality_flags',[]),mapping_version=s.get('mapping_version'),mode=s['mode'],radius_m=run['radius_m'],k_kw=200,q95=run['q95'],provider_inventory=s.get('provider_inventory',False))
    def station(self,data,sid):
        s=next((s for s in data.get('map_stations',data['stations']) if s['id']==sid),None)
        if s is None: raise ApiError(404,'시설을 찾을 수 없습니다.')
        return s
    def quality(self):
        assets=[a for a in self.store.all('assets') if a.get('type') in ('demand','sessions')]; demand=self.jsonfile('demand.json',{}); matches=self.store.all('matches'); collected=self.store.latest('collections')
        providers=collected.get('providers',{}) if collected else {k:dict(status='collection_pending' if os.getenv(v) else 'connection_pending') for k,v in (('ME','ME_SERVICE_KEY'),('KEPCO','KEPCO_SERVICE_KEY'))}
        if self.external:
            providers={key:dict(status='collected' if value['connected'] else (value.get('error') or {}).get('kind','not_collected'),count=value['count'],last_success_at=value['last_success_at'],authenticated_response=value['connected']) for key,value in self.external.status()['providers'].items()}
        return dict(assets=assets,providers=providers,collection=collected,matches=matches,source_names=sorted(demand),candidate_count=len(demand),approved_count=sum(m.get('status')=='approved' and not m.get('external_network') for m in matches),hourly=self.jsonfile('hourly.json',None),collection_enabled=self.external.collection_enabled if self.external else None)
    def dispatch(self,method,path,q=None,body=None,headers=None):
        q=q or {}; body=body or {}; headers=headers or {}
        if path=='/api/v1/health': return dict(status='ok',app_version='dashboard-v0.2',formula_version=FORMULA_VERSION,storage='postgresql' if self.store.pg else 'sqlite',server_time=now())
        if path=='/api/v1/data-quality':
            s=self.store.latest('snapshots')
            return dict(self.quality(),snapshot_id=s['id'] if s else None,analysis_run_id=None,observed_at=s['observed_at'] if s else None,demand_period=['2025-01-01','2025-12-31'],formula_version=FORMULA_VERSION,quality_flags=['실관측 미수집'] if not s else s.get('quality_flags',[]))
        if path=='/api/v1/admin/matches' and method=='GET':
            quality=self.quality(); snap=self.external.legacy_snapshot() if self.external else self.store.latest('snapshots'); stations=snap['stations'] if snap else []
            def norm(x): return re.sub(r'\s+','',x)
            quality['candidates']=[dict(source_name=name,candidates=[dict(station_id=s['id'],name=s['name'],address=s.get('address'),lat=s.get('lat'),lon=s.get('lon'),similarity=round(SequenceMatcher(None,norm(name),norm(s['name'])).ratio(),3)) for s in sorted(stations,key=lambda s:SequenceMatcher(None,norm(name),norm(s['name'])).ratio(),reverse=True)[:3]]) for name in quality['source_names']]
            quality['stations']=[dict(id=s['id'],name=s['name'],address=s.get('address'),lat=s.get('lat'),lon=s.get('lon')) for s in stations]
            return quality
        if path.startswith('/api/v1/admin/matches/') and method=='PATCH':
            token=os.getenv('ADMIN_TOKEN','')
            if not token or not hmac.compare_digest(headers.get('authorization',''),'Bearer '+token): raise ApiError(401,'서버 ADMIN_TOKEN과 일치하는 관리자 인증이 필요합니다.')
            sid=path.rsplit('/',1)[-1]; status=body.get('status'); name=body.get('source_name'); evidence=body.get('evidence','').strip(); reviewer=body.get('reviewer','').strip()
            if status not in ('approved','review_required','rejected','unmatched') or not evidence or not reviewer or (name!='__external_network__' and name not in self.jsonfile('demand.json',{})): raise ApiError(422,'원자료 시설명·검토상태·근거·검토자를 입력하세요.')
            snap=self.external.legacy_snapshot() if self.external else self.store.latest('snapshots')
            if not snap: raise ApiError(409,'수집된 시설이 없습니다.')
            self.station(snap,sid)
            others=[m for m in self.store.all('matches') if m.get('source_name')==name and m.get('status')=='approved' and m.get('station_id')!=sid]
            if status=='approved' and name!='__external_network__' and others: raise ApiError(409,'같은 원자료 명칭이 다른 시설에 이미 승인되어 있습니다. 다대다 연결을 별도 검토하세요.')
            m=dict(body,station_id=sid,external_network=name=='__external_network__',reviewed_at=now(),version='manual-v1')
            self.store.put('matches',m,sid); return m
        if path=='/api/v1/simulations' and method=='POST':
            run=self.store.get('runs',body.get('analysis_run_id',''))
            if not run: raise ApiError(404,'기준 실행을 찾을 수 없습니다.')
            if run.get('formula_version')!=FORMULA_VERSION: raise ApiError(409,'영향도 공식이 변경되었습니다. 새 분석을 실행하세요.')
            ids=body.get('charger_ids',[])
            if not isinstance(ids,list) or not all(isinstance(x,str) for x in ids): raise ApiError(422,'charger_ids는 문자열 배열입니다.')
            if run['snapshot']['mode']=='live':
                cs={c['id']:c for s in run['snapshot']['stations'] for c in s['chargers']}
                if any(i not in cs or not fresh(cs[i],now()) for i in ids): raise ApiError(409,'선택 설비의 상태 최신성이 만료되었습니다. 새 관측으로 다시 계산하세요.')
            try: result=simulate(run['snapshot'],run,ids)
            except ValueError as e: raise ApiError(409,str(e))
            current=self.snapshot(run['snapshot']['mode'])
            result.update(self.meta(run),previous_observation=current['id']!=run['snapshot']['id'])
            result['simulation_id']=self.store.put('simulations',dict(analysis_run_id=run['id'],charger_ids=result['charger_ids'],recovered_kw=result['recovered_kw']))
            return result
        if method!='GET': raise ApiError(405,'지원하지 않는 메서드입니다.')
        run=self.run(q); meta=self.meta(run); data=analyze(run['snapshot'],run['radius_m'],run['evaluated_at'],run['q95'])
        if path=='/api/v1/overview': return dict(meta,**data)
        if path=='/api/v1/priorities': return dict(meta,items=data['priorities'],held=data['held'])
        if path=='/api/v1/stations':
            items=data['stations']
            if q.get('district'): items=[s for s in items if s.get('district')==q['district']]
            if q.get('name'): items=[s for s in items if q['name'].lower() in s['name'].lower()]
            if q.get('status'): items=[s for s in items if any(c['display_status']==q['status'] for c in s['chargers'])]
            try:
                if q.get('bbox'):
                    lo,la,hi,ha=map(float,q['bbox'].split(',')); items=[s for s in items if s.get('lon') is not None and s.get('lat') is not None and lo<=s['lon']<=hi and la<=s['lat']<=ha]
                page=int(q.get('page',1)); size=int(q.get('page_size',100))
                if page<1 or size<1 or size>1000: raise ValueError()
            except (ValueError,TypeError): raise ApiError(422,'페이지 또는 bbox 형식이 잘못되었습니다.')
            return dict(meta,items=items[(page-1)*size:page*size],total=len(items),page=page,page_size=size)
        found=re.fullmatch(r'/api/v1/stations/([^/]+)(?:/(alternatives|maintenance))?',path)
        if found:
            sid,kind=found.groups(); station=self.station(data,sid)
            if kind=='alternatives': return dict(meta,items=alternatives(station,run['snapshot']['stations'],run['radius_m'],run['evaluated_at']),distance_type='직선거리')
            if kind=='maintenance':
                try: duration=int(q.get('duration_minutes',60)); weekday=int(q.get('weekday',0)); allowed_start=int(q.get('allowed_start',0)); allowed_end=int(q.get('allowed_end',1560))
                except (ValueError,TypeError): raise ApiError(422,'길이·요일·작업시간을 확인하세요.')
                if duration not in (60,120) or weekday not in range(7) or not 0<=allowed_start<1440 or not allowed_start<allowed_end<=1560: raise ApiError(422,'정비시간 범위를 확인하세요.')
                if q.get('year','2025')!='2025': raise ApiError(422,'현재 등록된 정비 분석기간은 2025년입니다.')
                if self.sessions is None:
                    p=DATA/'sessions.json.gz'
                    if p.exists():
                        with gzip.open(p,'rt',encoding='utf-8') as f: self.sessions=json.load(f)
                    else: self.sessions={}
                rows=self.sessions.get(station.get('source_name',station['name']),[])
                sessions=[(datetime.fromisoformat(r[0]),datetime.fromisoformat(r[1])) for r in rows]
                result=maintenance(sessions,station.get('covered_days'),station.get('fast_only_history_verified',False),weekday,duration,datetime(2025,1,1,tzinfo=KST),datetime(2026,1,1,tzinfo=KST),allowed_start,allowed_end)
                return dict(meta,**result,unit='세션·분',weekday=weekday,duration_minutes=duration,hourly=session_hourly(sessions,datetime(2025,1,1,tzinfo=KST),datetime(2026,1,1,tzinfo=KST)))
            kepco=next((a for a in self.store.all('assets') if a.get('type')=='kepco'),None)
            links={x['charger_id']:x['secondary_id'] for x in self.store.all('links') if x.get('approved')}
            comparison=cross_validate(station['chargers'],kepco.get('rows',[]) if kepco else [],links,kepco.get('field_map',{}) if kepco else {},json.loads(os.getenv('KEPCO_STATUS_MAP','{}')))
            return dict(meta,station=station,cross_validation=comparison)
        raise ApiError(404,'경로를 찾을 수 없습니다.')
