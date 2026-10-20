import math
import logging
import threading
import os
import uuid
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from urllib.parse import urlsplit
from .settings import Settings, ROOT
from .storage import Storage, now
from .services.me_api import MEAPI, model, classifications
from .services.kepco_api import KEPCOAPI
from .services.transport import ProviderError, requests_transport

class InternalError(Exception):
    def __init__(self, status, detail):
        self.status, self.detail = status, detail
        super().__init__('internal_api_error')

def error_response(error):
    return {'status':'error', 'source':'ME', 'error_type':error.detail.get('kind','internal_error')}

class ExternalService:
    def __init__(self, settings=None, storage=None, transport=requests_transport):
        self.settings = settings or Settings.load()
        self.storage = storage or Storage()
        self.transport = transport
        self.lock = threading.Lock()
        self.me_lock = threading.Lock()
        self.collecting = False
        self.runtime = 'collector'
        self.collection_enabled = True
        self.collection_started_at = None
        self.instance_id = os.environ.get('CHARGEOPS_INSTANCE_ID') or uuid.uuid4().hex

    def diagnose(self):
        url = self.settings.get('ME_URL')
        try:
            # Public domain connectivity can be diagnosed before an API URL is set.
            parts = urlsplit(url or 'https://apis.data.go.kr/')
            if parts.scheme != 'https' or parts.hostname != 'apis.data.go.kr' or parts.username or parts.password:
                raise ProviderError('invalid_url')
            status, _ = self.transport('https://' + parts.netloc + '/', {})
            return {'reachable': True, 'http_status': status,
                    'error': ProviderError('http_error', status).public() if not 200 <= status < 300 else None}
        except ProviderError as error:
            return {'reachable': False, 'error': error.public()}
        except ValueError:
            return {'reachable': False, 'error': ProviderError('invalid_url').public()}

    def reset_runtime(self):
        """Lifespan boundary: persisted errors belong to history, not this process."""
        for provider in ('ME','KEPCO','network'):
            state = self.storage.state(provider)
            history = list(state.get('history', []))
            previous = state.get('error')
            if previous and previous.get('kind') != 'not_collected':
                history.append({'error':previous, 'last_attempt_at':state.get('last_attempt_at'),
                                'instance_id':state.get('instance_id')})
            state.update(connected=False,error=None,current_error=None,last_attempt_at=None,
                         http_status=None,stage='pending',instance_id=self.instance_id,
                         previous_error=previous,history=history[-8:])
            if provider=='network': state.update(reachable=None,context='current_server')
            self.storage.set_state(provider,state)

    def collect_me(self):
        # Manual and scheduled requests serialize; neither depends on the timer.
        with self.me_lock:
            self.collecting = True
            self.collection_started_at = now()
            stage = 'collection'
            logger = logging.getLogger('uvicorn.error')
            logger.info('[ME] collection started')
            def event(name):
                nonlocal stage
                if name=='request started':
                    stage='request'
                    state=self.storage.state('ME')
                    attempted=now()
                    if attempted<=self.collection_started_at:
                        attempted=(datetime.fromisoformat(self.collection_started_at)+timedelta(microseconds=1)).isoformat()
                    state.update(last_attempt_at=attempted,error=None,current_error=None,
                                 stage=stage,instance_id=self.instance_id)
                    self.storage.set_state('ME',state)
                elif name=='HTTP response received': stage='response'
                elif name.startswith('parsing'): stage='parsing'
                if name!='request started':
                    state=self.storage.state('ME');state['stage']=stage
                    self.storage.set_state('ME',state)
                logger.info('[ME] %s',name)
            client = MEAPI(self.settings,self.transport,on_event=event)
            try:
                rows=client.fetch()
                logger.info('[ME] fetched count = %d',len(rows))
                stage='database'
                state=self.storage.state('ME');state['stage']=stage
                self.storage.set_state('ME',state)
                timestamp=now()
                self.storage.save_me(rows,timestamp,client.http_status)
                self.storage.set_state('network',{'reachable':True,'http_status':client.http_status,
                                                'error':None,'current_error':None,'context':'current_server'})
                logger.info('[ME] database stored = %d',len(rows))
                logger.info('[ME] collection completed')
                return {'status':'success','fetched':len(rows),'stored':len(rows),'collected_at':timestamp}
            except Exception as error:
                public=error.public() if isinstance(error,ProviderError) else {
                    'kind':'internal_error','message':'Collection processing error','http_status':None}
                state=self.storage.state('ME')
                state.update(connected=False,error=public,current_error=public,
                             http_status=public['http_status'],stage=stage,instance_id=self.instance_id)
                self.storage.set_state('ME',state)
                # A parse or database error cannot prove that the network is down.
                self.storage.set_state('network',{'reachable':True if stage in ('response','parsing','database') else None,
                                                'error':public if stage=='request' else None,'context':'current_server'})
                logger.error('[ME] collection failed stage=%s error_type=%s',stage,public['kind'])
                return {'status':'error','stage':stage,'error_type':public['kind'],'message':public['message']}
            finally:
                self.collecting=False

    def refresh(self):
        if not self.lock.acquire(blocking=False): return
        try:
            self.collect_me()
            client=KEPCOAPI(self.settings,self.transport)
            try:
                rows=client.fetch()
                self.storage.save_kepco(rows,now(),client.http_status)
            except Exception as error:
                public=error.public() if isinstance(error,ProviderError) else {
                    'kind':'internal_error','message':'Collection processing error','http_status':None}
                previous=self.storage.state('KEPCO')
                previous.update(connected=False,last_attempt_at=now(),error=public,current_error=public,
                                http_status=public['http_status'])
                self.storage.set_state('KEPCO',previous)
        finally:
            self.lock.release()

    def is_fresh(self):
        state = self.storage.state('ME')
        try:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(state['last_success_at'])).total_seconds()
            return state['connected'] and 0 <= age <= 900
        except (ValueError, TypeError, KeyError): return False

    def status(self):
        # Capture the in-memory flag before reading committed provider state.
        # Otherwise a response can combine pre-commit metadata with a post-commit
        # collecting=False flag and look like a completed but unattempted job.
        collecting = self.collecting
        types, states = classifications(self.settings)
        providers={p:self.storage.state(p) for p in ('ME','KEPCO')}
        for state in providers.values(): state['current_error']=state.get('error')
        return {'runtime': self.runtime, 'collection_enabled':self.collection_enabled,
                'uses_project_venv':Path(sys.prefix).resolve()==(ROOT/'.venv').resolve(),
                'collection_started_at':self.collection_started_at,
                'collection_revision':2,
                'last_me_attempt_at':providers['ME'].get('last_attempt_at'),
                'last_me_success_at':providers['ME']['last_success_at'],
                'last_kepco_success_at':providers['KEPCO']['last_success_at'],
                'stored_charger_count':self.storage.charger_count(),
                'recent_errors':{p:(s.get('error') or {}).get('kind') for p,s in providers.items()},
                'process_id':os.getpid(),'instance_id':self.instance_id,
                'environment': self.settings.presence(), 'providers':providers,
                'network': self.storage.state('network'), 'collecting': collecting,
                'stale': not self.is_fresh(), 'classification_verified': bool(types and states),
                'statusClassificationVerified': bool(states), 'chargerTypeClassificationVerified': bool(types)}

    def chargers(self):
        state = self.storage.state('ME')
        if self.collecting and not state['connected']:
            raise InternalError(503,{'kind':'collection_in_progress','message':'환경공단 데이터를 수집 중입니다.'})
        if state['last_success_at'] is None or not state['connected']:
            raise InternalError(503, {'kind': (state.get('error') or {}).get('kind', 'not_collected'),
                                      'message': ('환경공단 수집 대기 · ' if (state.get('error') or {}).get('kind')=='not_collected' else '환경공단 API 연결 실패 · ')+('데이터 미수집 · 마지막 성공 수집 없음' if state['last_success_at'] is None else '마지막 성공 수집 데이터는 별도로 보관됨'),
                                      'cause': state.get('error'), 'last_success_at': state['last_success_at']})
        fresh = self.is_fresh()
        types, states = classifications(self.settings)
        rows = [model(row, self.settings, stamp, fresh) for row, stamp in self.storage.rows()]
        eligible = [r for r in rows if r['analysis_eligible']]
        return {'items': eligible, 'total': len(eligible), 'inventory_count': len(rows),
                'unclassified_items': [r for r in rows if not r['classification_verified'] and r.get('delYn') != 'Y'],
                'last_success_at': state['last_success_at'], 'stale': not fresh,
                'error': state.get('error'), 'classification_verified': bool(types and states),
                'statusClassificationVerified': bool(states), 'chargerTypeClassificationVerified': bool(types)}

    def station(self, stat_id):
        rows = [model(row, self.settings, stamp, self.is_fresh()) for row, stamp in self.storage.rows() if str(row['statId']) == stat_id]
        if not rows:
            if self.storage.state('ME')['last_success_at'] is None: self.chargers()
            raise InternalError(404, {'kind': 'not_found', 'message': '충전소를 찾을 수 없습니다.'})
        comparisons = self.storage.comparison(stat_id) if self.storage.state('KEPCO')['connected'] else []
        for comparison in comparisons:
            source = next((r for r in rows if str(r['chgerId']) == comparison['charger_id']), None)
            comparison['matches'] = None
            comparison['temporal_verification'] = '비교 시각 확인 불가'
            try:
                def stamp(value):
                    if len(value) == 14 and value.isdigit():
                        return datetime.strptime(value, '%Y%m%d%H%M%S').replace(tzinfo=timezone(timedelta(hours=9)))
                    parsed = datetime.fromisoformat(value)
                    if parsed.tzinfo is None: raise ValueError()
                    return parsed
                source_time = stamp(source.get('statUpdDt'))
                secondary_time = stamp(comparison['api_updated_at'])
                age = (datetime.now(timezone.utc) - stamp(comparison['collected_at'])).total_seconds()
                aligned = abs((source_time-secondary_time).total_seconds()) <= 300 and 0 <= age <= 900
                comparison['temporal_verification'] = '상태 변경시각 차이 5분 이내' if aligned else '비교 시각 범위 초과'
                if aligned and self.is_fresh() and source['status'] != 'UNKNOWN' and comparison['secondary_status'] != 'UNKNOWN':
                    comparison['matches'] = source['status'] == comparison['secondary_status']
            except (ValueError, TypeError, AttributeError): pass
        return {'statId': stat_id, 'chargers': rows, 'cross_validation': comparisons,
                'cross_validation_status': 'mapped' if comparisons else '한전 교차검증: 미검증', 'stale': not self.is_fresh()}

    def legacy_snapshot(self):
        """Adapt real SQLite inventory to the established D1/D2 analysis model."""
        try: self.chargers()
        except InternalError as error:
            from services.api import ApiError
            raise ApiError(503, error.detail['message']) from None
        state = self.storage.state('ME'); groups = {}
        types, _ = classifications(self.settings)
        for raw, stamp in self.storage.rows():
            row = model(raw,self.settings,stamp,self.is_fresh())
            if row.get('delYn')=='Y': continue
            sid = 'ME:'+str(row['statId'])
            station = groups.setdefault(sid,dict(id=sid,name=row.get('statNm') or str(row['statId']),
                address=row.get('addr') or '',district=next((part for part in (row.get('addr') or '').split() if part.endswith('구')),'미확인'),
                lat=row['latitude'],lon=row['longitude'],chargers=[],annual_kwh=None,monthly_kwh=None,
                match_status='unmatched',quality_flags=[]))
            station['chargers'].append(dict(id=sid+':'+str(row['chgerId']),status=row['status'],power_kw=row['output_kw'],
                source_station_id=row['statId'],source_charger_id=row['chgerId'],source_updated_at=row.get('statUpdDt'),
                last_verified_at=stamp if row['classification_verified'] else None,ttl_minutes=15,
                fast_verified=str(row.get('chgerType')) in types,physical_verified=False,sharing_verified=False,
                access_verified=row.get('limitYn')=='N',compatible_verified=False,deleted=False))
        return dict(id='ME:'+state['last_success_at'],observed_at=state['last_success_at'],stations=list(groups.values()),
                    mode='live',network_complete=True,provider_inventory=True,quality_flags=[] if types else ['상태·급속 유형 분류 검증 대기'])

    def alternatives(self, stat_id, radius):
        if radius not in (500, 1000): raise InternalError(422, {'kind': 'invalid_radius', 'message': 'radius는 500 또는 1000입니다.'})
        station = self.station(stat_id)
        origin = next((r for r in station['chargers'] if r['latitude'] is not None and r['longitude'] is not None), None)
        if origin is None: raise InternalError(422, {'kind': 'missing_coordinates', 'message': '기준 충전소 좌표가 없습니다.'})
        result = []
        for row in self.chargers()['items']:
            if str(row['statId']) == stat_id or row['status'] not in ('AVAILABLE', 'CHARGING'): continue
            a, b = map(math.radians, (origin['latitude'], row['latitude']))
            dlat, dlon = b-a, math.radians(row['longitude'] - origin['longitude'])
            distance = 6371008.8 * 2 * math.asin(math.sqrt(min(1., math.sin(dlat/2)**2 + math.cos(a)*math.cos(b)*math.sin(dlon/2)**2)))
            if distance <= radius: result.append(dict(row, distance_m=round(distance, 1)))
        return {'items': sorted(result, key=lambda r:r['distance_m']), 'radius': radius, 'stale': not self.is_fresh(),
                'distance_type': '직선거리', 'normal_includes': ['AVAILABLE', 'CHARGING']}

    def dispatch(self, path, query=None):
        query = query or {}
        if path == '/api/system/status': return self.status()
        if path == '/api/chargers': return self.chargers()
        prefix = '/api/chargers/'
        if path.startswith(prefix):
            tail = path[len(prefix):].split('/')
            if len(tail) == 1: return self.station(tail[0])
            if len(tail) == 2 and tail[1] == 'alternatives':
                try: radius = int(query.get('radius', 500))
                except (ValueError, TypeError): raise InternalError(422, {'kind': 'invalid_radius', 'message': 'radius는 정수입니다.'}) from None
                return self.alternatives(tail[0], radius)
        raise InternalError(404, {'kind': 'not_found', 'message': '경로를 찾을 수 없습니다.'})
