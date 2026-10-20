"""Isolated fixtures only: never write test chargers to the live SQLite DB."""
import errno
import json
import os
import socket
import ssl
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch
from backend.app.settings import Settings, read_env
from backend.app.storage import Storage, now
from backend.app.core import ExternalService, InternalError
from backend.app.services.me_api import MEAPI, model
from backend.app.services.kepco_api import KEPCOAPI
from backend.app.services.transport import ProviderError, classify, decode, get_document, request

def settings():
    return Settings({'ME_URL':'https://apis.data.go.kr/fixture','ME_SERVICE_KEY':'UNIT_TEST_SECRET',
        'ME_MAPPING_VERIFIED':'true','ME_FAST_TYPES':'["DC_TEST"]',
        'ME_STATUS_MAP':'{"ready":"AVAILABLE","busy":"CHARGING","down":"STOPPED","inspect":"MAINTENANCE"}'})

def row(sid='A', state='ready', longitude='126.978'):
    return dict(statId=sid,chgerId='01',statNm='TEST FIXTURE ONLY',addr='서울특별시 중구',lat='37.5665',lng=longitude,
                chgerType='DC_TEST',output='100',stat=state,statUpdDt='20260101120000',limitYn='N',delYn='N')

def page(rows, total=None, number=1):
    return {'response':{'header':{'resultCode':'00'},'body':{'totalCount':len(rows) if total is None else total,'pageNo':number,'items':{'item':rows}}}}

class ExternalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db=Storage(Path(self.tmp.name)/'test.sqlite')

    def test_env_root_only_and_bom_quotes(self):
        p=Path(self.tmp.name)/'.env';p.write_text('\ufeffME_SERVICE_KEY="local-key" # comment\nexport ME_URL=local-url # comment\nKEPCO_URL=\n',encoding='utf-8')
        with patch.dict(os.environ,{'ME_SERVICE_KEY':'ambient-key'}):
            s=Settings(read_env(p));self.assertEqual(s.get('ME_SERVICE_KEY'),'local-key');self.assertFalse(s.presence()['KEPCO_URL'])
            self.assertNotIn('local-key',repr(s))

    def test_all_network_error_categories(self):
        cases=[(socket.gaierror(),'dns_error'),(ssl.SSLError(),'ssl_error'),(TimeoutError(),'timeout'),
               (ConnectionRefusedError(),'connection_refused'),(PermissionError(errno.EACCES,'fixture'),'network_permission_denied')]
        for e,kind in cases:
            with self.subTest(kind=kind):self.assertEqual(classify(urllib.error.URLError(e)).kind,kind)

    def test_json_and_xml_parse_same_inventory(self):
        data=decode(json.dumps(page([row()])).encode())
        self.assertEqual(data['response']['body']['items']['item'][0]['statId'],'A')
        xml=b'<response><header><resultCode>00</resultCode></header><body><totalCount>1</totalCount><pageNo>1</pageNo><items><item><statId>A</statId><chgerId>01</chgerId></item></items></body></response>'
        client=MEAPI(settings(),lambda *_:(200,xml));self.assertEqual(client.fetch(),[{'statId':'A','chgerId':'01'}])

    def test_auth_http_and_quota(self):
        for status,code,kind in [(200,'30','api_authentication_error'),(403,'','api_authentication_error'),(500,'','http_error'),(200,'22','quota_exceeded')]:
            with self.subTest(kind=kind):
                with self.assertRaises(ProviderError) as caught:
                    get_document('unused',{},lambda *_:(status,json.dumps({'resultCode':code}).encode()))
                self.assertEqual(caught.exception.kind,kind);self.assertEqual(caught.exception.http_status,status)

    def test_missing_fields_and_secret_echo_removed(self):
        r=row();r['statNm']='UNIT_TEST_SECRET';r['ServiceKey']='UNIT_TEST_SECRET'
        client=MEAPI(settings(),lambda *_:(200,json.dumps(page([r])).encode()))
        result=client.fetch()[0]
        self.assertNotIn('useTime',result);self.assertNotIn('ServiceKey',result);self.assertNotIn('UNIT_TEST_SECRET',json.dumps(result))
        self.assertNotIn('UNIT_TEST_SECRET',settings().redact('UNIT_TEST_SECRET'))

    def test_no_partial_publish_on_second_page_failure(self):
        self.db.save_me([row()],now(),200)
        def transport(url,params):
            if url.endswith('/'):return 200,b'{}'
            if params['pageNo']==1:return 200,json.dumps(page([row()],2)).encode()
            raise ProviderError('timeout')
        s=ExternalService(settings(),self.db,transport);s.refresh()
        self.assertEqual(len(self.db.rows()),1);self.assertEqual(s.status()['providers']['ME']['error']['kind'],'timeout')
        with self.assertRaises(InternalError) as caught:s.chargers()
        self.assertEqual(caught.exception.status,503)
        self.assertEqual(s.station('A')['chargers'][0]['status'],'UNKNOWN')

    def test_snapshot_time_semantics_and_endpoint_return(self):
        timestamp=now();self.db.save_me([row(),row('B','busy','126.979'),row('C','down','126.980')],timestamp,200)
        s=ExternalService(settings(),self.db)
        self.assertEqual(s.dispatch('/api/chargers')['total'],3)
        self.assertEqual(s.dispatch('/api/chargers/A')['chargers'][0]['statId'],'A')
        self.assertEqual([r['statId'] for r in s.alternatives('A',500)['items']],['B'])
        with self.db.connection() as db:
            r=db.execute('SELECT api_updated_at,collected_at FROM status_snapshots LIMIT 1').fetchone()
        self.assertEqual(r,('20260101120000',timestamp))
        with self.assertRaises(InternalError):s.alternatives('A',501)

    def test_no_mock_when_empty(self):
        s=ExternalService(settings(),self.db)
        with self.assertRaises(InternalError) as caught:s.chargers()
        self.assertEqual(caught.exception.status,503);self.assertEqual(self.db.rows(),[])

    def test_kepco_does_not_guess_contract(self):
        s=Settings({'KEPCO_SERVICE_KEY':'UNIT_TEST_SECRET','KEPCO_URL':'https://example.invalid/api'})
        called=[]
        with self.assertRaises(ProviderError) as caught:KEPCOAPI(s,lambda *a:called.append(a)).fetch()
        self.assertEqual(caught.exception.kind,'schema_unverified');self.assertEqual(called,[])

    def test_unverified_classification_and_deleted_excluded(self):
        s=Settings({});r=model(row(),s,now());self.assertFalse(r['analysis_eligible']);self.assertEqual(r['status'],'UNKNOWN')
        for change in [{'delYn':'Y'},{'limitYn':'Y'},{'lat':'nan'},{'output':'-5'}]:
            self.assertFalse(model(dict(row(),**change),settings(),now())['analysis_eligible'])

    def test_failure_diagnostics_never_echo_exception(self):
        def denied(*_):raise ProviderError('network_permission_denied')
        s=ExternalService(settings(),self.db,denied);s.refresh();body=json.dumps(s.status())
        self.assertNotIn('UNIT_TEST_SECRET',body);self.assertNotIn('https://apis.data.go.kr/fixture',body)
        self.assertEqual(s.status()['network']['error']['kind'],'network_permission_denied')

    def test_disallow_xml_entities(self):
        with self.assertRaises(ProviderError):decode(b'<!DOCTYPE x [<!ENTITY x "test">]><x>&x;</x>')

    def test_kepco_contract_and_no_time_comparison(self):
        contract={'verified':True,'source':'unit-test contract','key_param':'approvedKey',
                  'items_path':'records','id_field':'equipment','status_field':'condition',
                  'status_map':{'R':'AVAILABLE'}}
        s=settings();s.values.update(KEPCO_URL='https://example.invalid/fixture',KEPCO_SERVICE_KEY='UNIT_TEST_SECRET',KEPCO_CONTRACT=json.dumps(contract))
        client=KEPCOAPI(s,lambda *_:(200,b'{"records":[{"equipment":"K","condition":"R"}]}'))
        result=client.fetch();self.db.save_kepco(result,now(),200);self.db.save_me([row()],now(),200)
        with self.db.connection() as db:db.execute('INSERT INTO charger_links VALUES (?,?,?,?)',('A','01','K',1))
        comparison=ExternalService(s,self.db).station('A')['cross_validation'][0]
        self.assertIsNone(comparison['matches']);self.assertEqual(comparison['temporal_verification'],'비교 시각 확인 불가')

    def test_redirect_is_not_forwarded_and_encoded_key_once(self):
        from backend.app.services.transport import NoRedirect
        self.assertIsNone(NoRedirect().redirect_request(None,None,None,None,None,None))
        s=settings();s.values['ME_SERVICE_KEY']='UNIT%2BTEST%3D'
        seen=[]
        def transport(url,params):
            seen.append(params['serviceKey']);return 200,json.dumps(page([])).encode()
        MEAPI(s,transport).fetch();self.assertEqual(seen,['UNIT%2BTEST%3D'])

try:
    import fastapi, httpx
    from fastapi.testclient import TestClient
    HAVE_FASTAPI=True
except ImportError:HAVE_FASTAPI=False

@unittest.skipUnless(HAVE_FASTAPI,'FastAPI/httpx unavailable in this environment')
class FastAPITests(unittest.TestCase):
    setUp = ExternalTests.setUp
    def test_http_endpoints(self):
        from backend.app.main import create_app
        s=ExternalService(settings(),self.db)
        with TestClient(create_app(s,collect=False)) as client:
            failed=client.get('/api/chargers')
            self.assertEqual(failed.status_code,503)
            self.assertEqual(failed.json(),{'status':'error','source':'ME','error_type':'not_collected'})
            self.db.save_me([row()],now(),200)
            self.assertEqual(client.get('/api/chargers').json()['total'],1)
            self.assertEqual(client.get('/api/chargers/A').status_code,200)
            self.assertEqual(client.get('/api/chargers/A/alternatives?radius=700').status_code,422)
            self.assertNotIn('UNIT_TEST_SECRET',client.get('/api/system/status').text)
            for path in ('/.env','/apps/web/../../.env'):
                self.assertEqual(client.get(path).status_code,404)

if __name__=='__main__':unittest.main()
