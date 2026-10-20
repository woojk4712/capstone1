import asyncio
from contextlib import asynccontextmanager, suppress
from fastapi import FastAPI, Request, Query
from fastapi.responses import JSONResponse, FileResponse
from .core import ExternalService, InternalError, error_response
from .settings import ROOT
from .research import ResearchService as AnalysisService
from .operational_view import OperationalView, ObservationChanged
from .operational_recovery import OperationalRecovery
from pathlib import Path
import sys
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

def create_app(service=None, collect=True, public=False, public_origin=None):
    external = service or ExternalService()
    external.runtime = 'fastapi'
    external.collection_enabled = collect
    analysis = AnalysisService(external,Path(external.storage.path).parent/'analysis.sqlite')

    @asynccontextmanager
    async def lifespan(app):
        await asyncio.to_thread(external.reset_runtime)
        async def worker():
            while True:
                await asyncio.to_thread(external.refresh)
                await asyncio.sleep(900)
        task = asyncio.create_task(worker()) if collect else None
        yield
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError): await task

    app = FastAPI(title='Seoul Charge Ops', version='2.0.0', lifespan=lifespan)
    app.state.external = external

    @app.middleware('http')
    async def public_access(request, call_next):
        if public:
            path = request.url.path
            simulation = path in ('/api/operations/simulate', '/api/analysis/simulate')
            if path.startswith('/api/admin/') or path.startswith('/api/v1/admin/') or (
                request.method not in ('GET', 'HEAD', 'OPTIONS') and not (request.method == 'POST' and simulation)
            ):
                return JSONResponse(status_code=403, content={'detail': '공개 서버에서는 관리 변경을 허용하지 않습니다.'})
        return await call_next(request)
    operational = OperationalView(external)
    recovery = OperationalRecovery(operational,analysis)

    @app.exception_handler(ObservationChanged)
    async def observation_changed(request,error):
        return JSONResponse(status_code=409,content={'status':'error','error_type':'observation_changed',
                            'detail':'관측이 갱신되었습니다. 새로고침 후 같은 관측의 설비를 선택하세요.'})

    @app.middleware('http')
    async def fresh_ui(request, call_next):
        response = await call_next(request)
        if request.url.path in ('/', '/live', '/analysis') or request.url.path.startswith('/apps/web/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.get('/api/operations/observations')
    def operational_observations(observationAt: str=None): return operational.inventory(observationAt)

    @app.get('/api/operations/stations')
    def operational_stations(stopped_only: bool=False,observationAt: str=None):
        data = operational.stations(observationAt)
        if stopped_only:
            data['items'] = [s for s in data['items'] if any(str(c.get('stat'))=='4' for c in s['chargers'])]
            data['total'] = len(data['items'])
            data['chargerCount'] = sum(len(s['chargers']) for s in data['items'])
        return {**data,'status':'ok','count':data['total'],'stoppedChargerCount':sum(str(c.get('stat'))=='4' for s in data['items'] for c in s['chargers']),
                'reason':None if data['items'] else 'no_observed_stopped_chargers' if stopped_only else 'no_seoul_observations'}

    @app.get('/api/analysis/revision')
    def analysis_revision():
        stamp=external.storage.state('ME').get('last_success_at')
        return {'revision':str(analysis.path.stat().st_mtime_ns)+':'+str(stamp),'observationAt':stamp}

    @app.get('/api/analysis/recovery-ranking')
    def recovery_ranking(radius: int=500,replay: bool=False,observationAt: str=None):
        return operational_recovery(radius,replay,observationAt)

    @app.get('/api/operations/recovery')
    def operational_recovery(radius: int=500,replay: bool=False,observationAt: str=None):
        try:return recovery.ranking(radius,observationAt,replay)
        except ObservationChanged:raise
        except ValueError:return JSONResponse(status_code=422,content={'detail':'반경 또는 관측 입력 확인 필요'})

    @app.get('/api/analysis/potential-impact')
    def potential_impact(radius: int=500, weight: str='equal', preview: bool=False, replay: bool=False):
        return ranking_response(True, radius, weight, preview, replay)

    def ranking_response(potential, radius, weight, preview, replay):
        try:
            data = analysis.overview(radius, weight, preview, replay)
            items = data['potential' if potential else 'priorities']
            return {'status': 'stale' if data['stale'] and not replay else 'ok', 'count': len(items), 'items': items,
                    'reason': None if items else 'latest_observation_required' if data['stale'] and not replay else
                    'no_eligible_core_chargers' if potential else 'no_current_stopped_core_chargers',
                    'stale': data['stale'], 'replay': replay, 'observationAt': data['last_success_at']}
        except ValueError:
            return JSONResponse(status_code=422, content={'detail': '반경/가중치 선택 오류'})

    @app.post('/api/operations/simulate')
    async def operational_simulate(request: Request):
        if not local_write(request): return JSONResponse(status_code=403, content={'detail': '동일 출처 로컬 요청 필요'})
        try:
            body = await request.json()
            return await asyncio.to_thread(operational.simulate, body.get('chargerIds', []),
                                           body.get('stationIds', []), body.get('replay', False),body.get('observationAt'))
        except ObservationChanged:raise
        except (ValueError, TypeError):
            return JSONResponse(status_code=422, content={'detail': '관측시각과 서울 운영중지 설비 선택을 확인하세요'})

    @app.exception_handler(InternalError)
    async def internal_error(request, error):
        return JSONResponse(status_code=error.status, content=error_response(error))

    @app.get('/api/chargers')
    def chargers(): return external.chargers()

    @app.get('/api/analysis/overview')
    def research_overview(radius: int=500,weight: str='equal',preview: bool=False,replay: bool=False):
        try:
            data=analysis.overview(radius,weight,preview,replay)
            return {**data,'status':'stale' if data['stale'] and not replay else 'ok',
                    'count':data['total'],'reason':'latest_observation_required' if data['stale'] and not replay else None}
        except ValueError as e:return JSONResponse(status_code=422,content={'detail':str(e)})

    @app.get('/api/analysis/quality')
    def research_quality():
        operational_data=recovery.ranking()
        return {**analysis.quality(),'funnel':analysis.funnel(),
                'operationalRecovery':{'observationAt':operational_data['observationAt'],**operational_data['diagnostics']}}

    @app.get('/api/analysis/maintenance/{stat_id}')
    def research_maintenance(stat_id: str,preview: bool=False):
        try:return analysis.maintenance(stat_id,preview)
        except ValueError:return JSONResponse(status_code=404,content={'detail':'핵심 분석시설 없음'})

    def local_write(request):
        if public and request.url.path in ('/api/operations/simulate', '/api/analysis/simulate'):
            return request.headers.get('origin') == (public_origin or str(request.base_url).rstrip('/'))
        return request.client.host in ('127.0.0.1','::1','testclient') and request.headers.get('origin') in (None,str(request.base_url).rstrip('/'))

    @app.post('/api/analysis/matches/review')
    async def research_review(request: Request):
        if not local_write(request):return JSONResponse(status_code=403,content={'detail':'동일 출처의 로컬 검토만 허용합니다'})
        try:
            body=await request.json()
            return await asyncio.to_thread(analysis.review,str(body['d1StationName']),str(body['statId']),body['action'],str(body['evidence']))
        except (ValueError,KeyError,TypeError):return JSONResponse(status_code=422,content={'detail':'후보 및 독립 시설 확인 근거를 확인하세요'})

    @app.post('/api/analysis/simulate')
    async def research_simulate(request: Request):
        if not local_write(request):return JSONResponse(status_code=403,content={'detail':'동일 출처 로컬 요청 필요'})
        try:
            body=await request.json()
            return await asyncio.to_thread(analysis.simulate,body.get('chargerIds',[]),body.get('radius',500),body.get('weight','equal'),body.get('preview',False),body.get('hypothetical',False),body.get('replay',False))
        except (ValueError,TypeError):return JSONResponse(status_code=422,content={'detail':'최신 분석대상과 시나리오 입력을 확인하세요'})

    @app.get('/api/chargers/{statId}')
    def station(statId: str): return external.station(statId)

    @app.get('/api/chargers/{statId}/alternatives')
    def alternatives(statId: str, radius: int = Query(500)):
        return external.alternatives(statId, radius)

    @app.get('/api/system/status')
    def status(): return external.status()

    @app.get('/api/analysis/stations')
    def analysis_stations(): return analysis.stations()

    @app.get('/api/analysis/matches')
    def analysis_matches():
        return {'items':analysis.match_rows(),'summary':analysis.match_summary(),'d1':analysis.meta('d1')}

    @app.get('/api/analysis/stations/{statId}/alternatives')
    def analysis_alternatives(statId: str, radius: int = Query(500)):
        try:return analysis.alternatives(statId,radius)
        except ValueError:
            return JSONResponse(status_code=422,content={'status':'error','error_type':'analysis_station_or_radius_invalid'})

    @app.post('/api/admin/collect/me')
    async def collect_me(request: Request):
        # Development endpoint on the loopback server. Reject browser cross-origin
        # requests so opening a third-party page cannot trigger a collection.
        if request.headers.get('origin') not in (None,'http://127.0.0.1:8000','http://localhost:8000'):
            return JSONResponse(status_code=403,content={'status':'error','stage':'authorization',
                                'error_type':'origin_not_allowed','message':'Local origin required'})
        result=await asyncio.to_thread(external.collect_me)
        return JSONResponse(status_code=200 if result['status']=='success' else 503,content=result)

    from services.api import Service, ApiError
    legacy = Service(external=external,analysis=analysis)
    @app.api_route('/api/v1/{path:path}', methods=['GET', 'POST', 'PATCH'])
    async def legacy_route(path: str, request: Request):
        try:
            body = await request.json() if request.method != 'GET' else {}
            if not isinstance(body, dict): raise ApiError(422, 'JSON 객체가 필요합니다.')
            return await asyncio.to_thread(legacy.dispatch, request.method, '/api/v1/' + path, dict(request.query_params), body, dict(request.headers))
        except ApiError as error: return JSONResponse(status_code=error.status, content={'detail': error.message})
        except (ValueError, TypeError): return JSONResponse(status_code=422, content={'detail': '잘못된 입력입니다.'})

    @app.get('/')
    def dashboard(): return FileResponse(ROOT / 'apps/web/offline.html')

    @app.get('/live')
    def live(): return FileResponse(ROOT / 'apps/web/live.html')

    @app.get('/analysis')
    def analysis_page(): return FileResponse(ROOT / 'apps/web/analysis.html')

    @app.get('/apps/web/{path:path}')
    def assets(path: str):
        allowed = {'src/recovery-ui.js','src/research-tabs.js','src/research-ui.js','src/dashboard.js','src/dashboard-model.js','src/district-bounds.js','src/station-map.js','src/leaflet-map.js','src/style.css','src/live-api.js','src/live-api.css', 'vendor/leaflet.js','vendor/leaflet.css'}
        if path not in allowed or not (ROOT / 'apps/web' / path).is_file():
            return JSONResponse(status_code=404, content={'detail':'Not found'})
        return FileResponse(ROOT / 'apps/web' / path)
    return app

app = create_app()
