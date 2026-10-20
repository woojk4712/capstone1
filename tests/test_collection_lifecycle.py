"""Start the real FastAPI lifespan with injected transport, never real API keys."""
import json
import tempfile
import time
import unittest
from pathlib import Path
from backend.app.core import ExternalService
from backend.app.settings import Settings
from backend.app.storage import Storage

try:
    from fastapi.testclient import TestClient
    from backend.app.main import create_app
    HAVE_FASTAPI=True
except ImportError:HAVE_FASTAPI=False

@unittest.skipUnless(HAVE_FASTAPI,'FastAPI runtime unavailable')
class CollectionLifecycleTests(unittest.TestCase):
    def test_default_lifespan_collects_me_and_keeps_kepco_independent(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings=Settings({'ME_URL':'https://apis.data.go.kr/fixture/info','ME_STATUS_URL':'https://apis.data.go.kr/fixture/status',
                'ME_SERVICE_KEY':'FIXTURE_KEY_ONLY','ME_MAPPING_VERIFIED':'true',
                'ME_FAST_TYPES':'["TEST_FAST"]','ME_STATUS_MAP':'{"ready":"AVAILABLE","busy":"CHARGING"}'})
            calls=[]
            def transport(url,params):
                calls.append('status' if url.endswith('/status') else 'info')
                row={'statId':'FIXTURE','chgerId':'1','stat':'busy','statUpdDt':'20260101120000'} if url.endswith('/status') else {
                    'statId':'FIXTURE','chgerId':'1','statNm':'TEST FIXTURE ONLY','addr':'TEST ADDRESS',
                    'lat':'37.56','lng':'126.98','chgerType':'TEST_FAST','output':'100','stat':'ready',
                    'useTime':'TEST','limitYn':'N','limitDetail':'','delYn':'N'}
                return 200,json.dumps({'response':{'header':{'resultCode':'00'},'body':{'pageNo':1,'totalCount':1,'items':{'item':[row]}}}}).encode()
            service=ExternalService(settings,Storage(Path(tmp)/'fixture.sqlite'),transport)
            with TestClient(create_app(service)) as client:
                for _ in range(100):
                    status=client.get('/api/system/status').json()
                    if status['last_me_success_at'] is not None and not status['collecting']:break
                    time.sleep(.01)
                self.assertTrue(status['collection_enabled']);self.assertEqual(status['runtime'],'fastapi')
                self.assertIsNotNone(status['collection_started_at']);self.assertEqual(status['stored_charger_count'],1)
                self.assertEqual(status['recent_errors']['ME'],None)
                self.assertTrue(all(isinstance(v,bool) for v in status['environment'].values()))
                response=client.get('/api/chargers');self.assertEqual(response.status_code,200)
                row=response.json()['items'][0];self.assertEqual(row['stat'],'busy')
                self.assertNotIn('FIXTURE_KEY_ONLY',response.text)
                self.assertEqual(calls,['info','status'])
                with service.storage.connection() as db:
                    saved=db.execute('SELECT api_updated_at,collected_at FROM status_snapshots').fetchone()
                self.assertEqual(saved[0],'20260101120000');self.assertNotEqual(saved[0],saved[1])

    def test_explicit_preview_never_invokes_transport(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls=[]
            service=ExternalService(Settings({}),Storage(Path(tmp)/'fixture.sqlite'),lambda *args:calls.append(args))
            with TestClient(create_app(service,collect=False)) as client:
                status=client.get('/api/system/status').json()
                self.assertFalse(status['collection_enabled']);self.assertIsNone(status['collection_started_at'])
            self.assertEqual(calls,[])

if __name__=='__main__':unittest.main()
