import json,threading,unittest,urllib.request,urllib.error
from http.server import HTTPServer
from services import local_server
from services.api import Service
from services.store import Store
class HttpTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.old=local_server.service;local_server.service=Service(Store(':memory:'));cls.server=HTTPServer(('127.0.0.1',0),local_server.Handler);cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start();cls.url=f'http://127.0.0.1:{cls.server.server_port}'
 @classmethod
 def tearDownClass(cls): cls.server.shutdown();cls.server.server_close();local_server.service=cls.old
 def get(self,path):
  try:
   with urllib.request.urlopen(self.url+path) as r: return r.status,r.read()
  except urllib.error.HTTPError as e: return e.code,e.read()
 def test_dashboard_document(self):
  code,body=self.get('/');self.assertEqual(code,200);self.assertIn(b'mountDashboard',body)
  code,body=self.get('/analysis');self.assertEqual(code,200);self.assertIn(b'mountDashboard',body)
 def test_private_file_allowlist(self):
  for path in ('/.env','/data/runtime/ops.sqlite','/services/config.py','/../.env','/reports/source-quality.json'):
   self.assertEqual(self.get(path)[0],404)
 def test_live_error_is_not_empty_success(self): self.assertEqual(self.get('/api/v1/overview')[0],503)
 def test_sample_explicit(self):
  code,raw=self.get('/api/v1/overview?mode=sample');body=json.loads(raw);self.assertEqual(code,200);self.assertEqual(body['mode'],'sample');self.assertEqual(len(body['stations']),24)
 def test_security_headers_and_assets(self):
  with urllib.request.urlopen(self.url+'/apps/web/src/dashboard.js') as r: self.assertEqual(r.headers['X-Content-Type-Options'],'nosniff');self.assertIn('javascript',r.headers['Content-Type'])
 def test_snapshot_response_consistency(self):
  _,raw=self.get('/api/v1/overview?mode=sample');b=json.loads(raw);station=b['stations'][0];_,raw=self.get('/api/v1/stations/'+station['id']+'?mode=sample&analysis_run_id='+b['analysis_run_id']);detail=json.loads(raw);self.assertEqual(detail['station']['totals'],station['totals']);self.assertEqual(detail['snapshot_id'],b['snapshot_id'])
 def test_external_api_http_contract(self):
  import tempfile
  from pathlib import Path
  from backend.app.core import ExternalService
  from backend.app.settings import Settings
  from backend.app.storage import Storage,now
  previous=local_server.external
  try:
   with tempfile.TemporaryDirectory() as tmp:
    local_server.external=ExternalService(Settings({}),Storage(Path(tmp)/'test.sqlite'))
    self.assertEqual(self.get('/api/chargers')[0],503)
    local_server.external.storage.save_me([dict(statId='HTTP_TEST',chgerId='01',statNm='HTTP fixture only')],now(),200)
    code,raw=self.get('/api/chargers');self.assertEqual(code,200);self.assertEqual(json.loads(raw)['inventory_count'],1)
    self.assertEqual(self.get('/api/chargers/HTTP_TEST')[0],200)
    self.assertEqual(self.get('/api/chargers/HTTP_TEST/alternatives?radius=600')[0],422)
    code,raw=self.get('/api/system/status');self.assertEqual(code,200);self.assertTrue(all(isinstance(v,bool) for v in json.loads(raw)['environment'].values()))
  finally:local_server.external=previous
if __name__=='__main__': unittest.main()
