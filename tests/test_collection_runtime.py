"""Use a blocked injected transport to observe real lifespan/request ordering."""
import contextlib
import io
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from backend.app.core import ExternalService
from backend.app.main import create_app
from backend.app.settings import Settings
from backend.app.storage import Storage
from backend.app.services import me_api
from backend.app.services.transport import ProviderError
from backend.app.local_tests import test_me as local_test_me


class RuntimeCollectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.db=Storage(Path(self.tmp.name)/'runtime.sqlite')
        self.settings=Settings({'ME_URL':'https://apis.data.go.kr/test/info','ME_SERVICE_KEY':'FIXTURE_KEY_NOT_REAL',
            'ME_MAPPING_VERIFIED':'true','ME_FAST_TYPES':'["TEST_FAST"]','ME_STATUS_MAP':'{"ready":"AVAILABLE"}'})

    def response(self):
        row={'statId':'FIXTURE','chgerId':'01','statNm':'Fixture only','lat':'37.56','lng':'126.98',
             'output':'100','chgerType':'TEST_FAST','stat':'ready','limitYn':'N','delYn':'N','statUpdDt':'20260101120000'}
        return 200,json.dumps({'response':{'header':{'resultCode':'00','resultMsg':'OK'},
            'body':{'pageNo':1,'totalCount':1,'items':{'item':[row]}}}}).encode()

    def test_new_lifespan_moves_old_error_to_history_before_http_finishes(self):
        old={'kind':'network_permission_denied','message':'Old process error','http_status':None}
        self.db.set_state('ME',{'connected':False,'last_success_at':None,'count':0,
                               'last_attempt_at':'2000-01-01T00:00:00+00:00','error':old})
        self.db.set_state('network',{'reachable':False,'error':old})
        entered,release=threading.Event(),threading.Event()
        def transport(*args):
            entered.set()
            if not release.wait(5): raise ProviderError('timeout')
            return self.response()
        service=ExternalService(self.settings,self.db,transport)
        with self.assertLogs('uvicorn.error',level='INFO') as logs:
            with TestClient(create_app(service)) as client:
                try:
                    self.assertTrue(entered.wait(2))
                    status=client.get('/api/system/status').json();current=status['providers']['ME']
                    self.assertTrue(status['collecting']);self.assertIsNone(current['current_error'])
                    self.assertIsNone(status['recent_errors']['ME']);self.assertIsNone(status['network']['error'])
                    self.assertEqual(current['history'][-1]['error']['kind'],'network_permission_denied')
                    self.assertGreater(current['last_attempt_at'],status['collection_started_at'])
                    attempted=current['last_attempt_at']
                finally: release.set()
                for _ in range(100):
                    status=client.get('/api/system/status').json()
                    if not status['collecting']:break
                    time.sleep(.01)
                self.assertEqual(status['stored_charger_count'],1)
                self.assertIsNotNone(status['last_me_success_at'])
                self.assertEqual(status['last_me_attempt_at'],attempted)
                self.assertEqual(client.get('/api/chargers').status_code,200)
                self.assertEqual(status['providers']['ME']['history'][-1]['error'],old)
        text='\n'.join(logs.output)
        for stage in ('collection started','request started','HTTP response received','parsing completed',
                      'fetched count = 1','database stored = 1','collection completed'):
            self.assertIn('[ME] '+stage,text)
        self.assertNotIn('FIXTURE_KEY_NOT_REAL',text);self.assertNotIn('https://',text)

    def test_manual_endpoint_runs_once_without_scheduler_and_uses_test_function(self):
        calls=[]
        def transport(url,params):calls.append(params);return self.response()
        service=ExternalService(self.settings,self.db,transport)
        with patch.object(me_api,'fetch_me_chargers',wraps=me_api.fetch_me_chargers) as shared:
            with TestClient(create_app(service,collect=False)) as client:
                self.assertEqual(calls,[])
                result=client.post('/api/admin/collect/me')
                self.assertEqual(result.status_code,200)
                self.assertEqual(result.json()['stored'],1);self.assertEqual(result.json()['fetched'],1)
                self.assertEqual(client.get('/api/chargers').status_code,200)
                self.assertEqual(len(calls),1)
                with contextlib.redirect_stdout(io.StringIO()):
                    local_test_me(transport,self.settings,Path(self.tmp.name)/'evidence.json')
                self.assertEqual(shared.call_count,2)
                self.assertNotIn('FIXTURE_KEY_NOT_REAL',result.text)

    def test_request_failure_has_new_attempt_and_safe_stage(self):
        def denied(*args): raise ProviderError('timeout')
        service=ExternalService(self.settings,self.db,denied)
        with TestClient(create_app(service,collect=False)) as client:
            result=client.post('/api/admin/collect/me')
            self.assertEqual(result.status_code,503)
            self.assertEqual(result.json()['stage'],'request')
            self.assertEqual(result.json()['error_type'],'timeout')
            status=client.get('/api/system/status').json()
            self.assertGreater(status['last_me_attempt_at'],status['collection_started_at'])
            self.assertFalse(status['collecting'])
            self.assertEqual(client.get('/api/chargers').status_code,503)

    def test_database_error_reports_database_stage_without_exception_message(self):
        service=ExternalService(self.settings,self.db,lambda *a:self.response())
        with TestClient(create_app(service,collect=False)) as client:
            with patch.object(self.db,'save_me',side_effect=RuntimeError('FIXTURE_KEY_NOT_REAL')):
                result=client.post('/api/admin/collect/me')
            self.assertEqual(result.json()['stage'],'database')
            self.assertNotIn('FIXTURE_KEY_NOT_REAL',result.text)
            self.assertFalse(service.collecting)

    def test_manual_endpoint_rejects_cross_origin_browser_request(self):
        calls=[]
        service=ExternalService(self.settings,self.db,lambda *a:calls.append(a))
        with TestClient(create_app(service,collect=False)) as client:
            self.assertEqual(client.post('/api/admin/collect/me',headers={'Origin':'https://other.invalid'}).status_code,403)
        self.assertEqual(calls,[])

if __name__=='__main__':unittest.main()
