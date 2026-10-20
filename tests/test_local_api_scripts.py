"""No real network calls: exercise local commands with injected responses."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from backend.app.settings import Settings, read_env, ROOT
from backend.app.local_tests import test_me as run_me, test_kepco as run_kepco
from backend.app.services.transport import requests_response, classify_requests, ProviderError
from backend.app.services.me_api import MEAPI
from backend.app.core import ExternalService
from backend.app.storage import Storage

class LocalScriptTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)
        self.settings=Settings({'ME_URL':'https://apis.data.go.kr/test','ME_STATUS_URL':'https://apis.data.go.kr/status',
            'ME_SERVICE_KEY':'NEVER_PRINT_THIS%2B','KEPCO_URL':'https://example.invalid/test','KEPCO_SERVICE_KEY':'SECOND_SECRET'})

    def test_whitespace_and_absolute_root(self):
        p=self.path/'.env';p.write_text('\ufeffME_SERVICE_KEY="\u00a0 A\u200bBC%2B \u3000"\nME_URL= \u00a0https://example.invalid/a\u200b\n',encoding='utf-8')
        values=read_env(p)
        self.assertEqual(values['ME_SERVICE_KEY'],'ABC%2B');self.assertEqual(values['ME_URL'],'https://example.invalid/a')
        from backend.app.settings import ENV_PATH
        self.assertTrue(ENV_PATH.is_absolute());self.assertEqual(ENV_PATH,ROOT/'.env')

    def test_me_success_fields_only_key_unchanged(self):
        seen=[]
        def transport(url,params):
            seen.append(params)
            return 200,'application/json',json.dumps({'response':{'header':{'resultCode':'00','resultMsg':'NEVER_PRINT_THIS%2B'},'body':{'pageNo':1,'totalCount':1,'items':{'item':[{'statId':'SECRET_ROW_VALUE','chgerId':'01','method':'DC','addrDetail':'not printed'}]}}}}).encode()
        output=io.StringIO()
        with contextlib.redirect_stdout(output): result=run_me(transport,self.settings,self.path/'me.json')
        self.assertEqual(result,0);self.assertEqual(seen[0]['serviceKey'],'NEVER_PRINT_THIS%2B')
        self.assertEqual(seen[0]['numOfRows'],10)
        self.assertNotIn('NEVER_PRINT_THIS',output.getvalue());self.assertNotIn('SECRET_ROW_VALUE',output.getvalue())
        evidence=json.loads((self.path/'me.json').read_text(encoding='utf-8'));self.assertFalse(evidence['mapping_verified'])
        self.assertIn('addrDetail',evidence['fields']);self.assertNotIn('SECRET_ROW_VALUE',str(evidence))

    def test_me_failure_types_and_no_exception_text(self):
        for kind in ('dns_error','ssl_error','timeout','connection_error','network_permission_denied','api_authentication_error','parameter_error','invalid_schema'):
            def denied(*args):raise ProviderError(kind)
            with self.subTest(kind=kind),contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(run_me(denied,self.settings,self.path/'none.json'),1)
                self.assertIn('ERROR TYPE:',out.getvalue());self.assertNotIn('NEVER_PRINT_THIS',out.getvalue())

    def test_requests_uses_params_and_no_redirect_or_decode(self):
        response=Mock();response.status_code=200;response.headers={'Content-Type':'application/json'};response.iter_content.return_value=[b'{}']
        response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        fake=Mock();fake.get.return_value=response
        with patch.dict(sys.modules,{'requests':fake}):
            self.assertEqual(requests_response(self.settings.get('ME_URL'),{'serviceKey':self.settings.get('ME_SERVICE_KEY')})[0],200)
        self.assertEqual(fake.get.call_args.kwargs['params']['serviceKey'],'NEVER_PRINT_THIS%2B')
        self.assertFalse(fake.get.call_args.kwargs['allow_redirects'])

    def test_requests_nested_error_categories(self):
        for name,kind in [('NameResolutionError','dns_error'),('SSLError','ssl_error'),('ReadTimeout','timeout'),('ConnectionError','connection_error')]:
            error=type(name,(Exception,),{})('NEVER_PRINT_THIS%2B')
            self.assertEqual(classify_requests(error).kind,kind)

    def test_kepco_request_separate_from_response_contract(self):
        contract=self.path/'contract.json'
        contract.write_text(json.dumps({'request_verified':True,'source':'TEST approved manual','key_param':'documentedKey',
            'response_format':'JSON','pagination':'none','required_params':['region'],'params':{'region':'TEST'}}),encoding='utf-8')
        def transport(url,params):
            self.assertEqual(params,{'region':'TEST','documentedKey':'SECOND_SECRET'})
            return 200,'application/json',b'{"records":[{"equipment":"VALUE_NOT_PRINTED","condition":"R"}]}'
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(run_kepco(transport,self.settings,contract,self.path/'kepco.json'),0)
        self.assertNotIn('SECOND_SECRET',out.getvalue());self.assertNotIn('VALUE_NOT_PRINTED',out.getvalue())
        self.assertIn('equipment',out.getvalue());self.assertFalse(json.loads((self.path/'kepco.json').read_text())['status_mapping_verified'])

    def test_kepco_unknown_request_never_sends_key(self):
        contract=self.path/'contract.json';contract.write_text('{"request_verified":false}',encoding='utf-8')
        calls=[]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(run_kepco(lambda *a:calls.append(a),self.settings,contract,self.path/'none.json'),1)
        self.assertEqual(calls,[])

    def test_status_updates_merge_only_provided_fields(self):
        def transport(url,params):
            row={'statId':'A','chgerId':'1','stat':'3','statUpdDt':'20260101120000'} if url.endswith('/status') else {'statId':'A','chgerId':'1','statNm':'Fixture only','addrDetail':'TEST','method':'DC','stat':'2'}
            return 200,json.dumps({'response':{'header':{'resultCode':'00'},'body':{'totalCount':1,'pageNo':1,'items':{'item':[row]}}}}).encode()
        rows=MEAPI(self.settings,transport).fetch()
        self.assertEqual(rows[0]['stat'],'3');self.assertEqual(rows[0]['method'],'DC');self.assertNotIn('output',rows[0])
        self.assertEqual(rows[0]['statUpdDt'],'20260101120000')

    def test_existing_dashboard_uses_real_inventory_without_kepco(self):
        from services.api import Service
        from services.store import Store
        db=Storage(self.path/'test.sqlite')
        from backend.app.storage import now
        db.save_me([{'statId':'REAL_ADAPTER_FIXTURE','chgerId':'1','statNm':'TEST ONLY','lat':'37.56','lng':'126.98','output':'100','stat':'2'}],now(),200)
        external=ExternalService(self.settings,db)
        service=Service(Store(':memory:'),external=external)
        result=service.dispatch('GET','/api/v1/overview',{'mode':'live'})
        self.assertTrue(result['provider_inventory']);self.assertEqual(len(result['map_stations']),1)
        self.assertEqual(result['map_stations'][0]['lat'],37.56);self.assertEqual(result['priorities'],[])
        self.assertEqual(service.quality()['providers']['ME']['status'],'collected')

if __name__=='__main__':unittest.main()
