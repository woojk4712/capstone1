"""Diagnostic verification uses injected responses only; no real API calls."""
import contextlib
import io
import json
import socket
import ssl
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from scripts import diagnose_local_api as diag
from backend.app.settings import Settings
from backend.app.services.transport import ProviderError


class LocalDiagnosisTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings({'ME_SERVICE_KEY':'TEST_SECRET%2B', 'KEPCO_SERVICE_KEY':'OTHER_TEST_SECRET',
                                  'ME_URL':'https://apis.data.go.kr/info',
                                  'ME_STATUS_URL':'https://apis.data.go.kr/status'})

    def response(self, code='00', message='NORMAL SERVICE'):
        return 200, 'application/json', json.dumps({'response':{'header':{'resultCode':code,'resultMsg':message},
            'body':{'totalCount':1,'pageNo':1,'items':{'item':[{'statId':'ITEM_VALUE_NOT_FOR_OUTPUT','chgerId':'01'}]}}}}).encode()

    def test_both_endpoints_once_metadata_only_and_safe_report(self):
        calls = []
        def get(url, params=None):
            calls.append((url, params))
            if url.endswith('/info') or url.endswith('/status'):
                return self.response(message='TEST_SECRET%2B https://example.invalid/?apiKey=UNRELATED_SECRET')
            if url.endswith('/api/system/status'):
                return 200,'application/json',json.dumps({'runtime':'fastapi','collection_enabled':True,
                    'last_me_success_at':None,'stored_charger_count':0,'recent_errors':{'ME':'network_permission_denied'},
                    'UNSAFE':'OTHER_TEST_SECRET'}).encode()
            if url.endswith('/api/chargers'):
                return 503,'application/json',b'{"error_type":"network_permission_denied","secret":"OTHER_TEST_SECRET"}'
            return 200,'text/html',b'HTTPS homepage never printed'
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()) as out:
            path=Path(tmp)/'diagnosis.txt'
            exit_code=diag.run(self.settings,get,lambda host:'DNS_OK',lambda:'SUCCESS',path)
            text=path.read_text(encoding='utf-8')
        self.assertEqual(exit_code,0)
        self.assertEqual(out.getvalue(),text)
        for secret in ('TEST_SECRET','OTHER_TEST_SECRET','UNRELATED_SECRET','ITEM_VALUE_NOT_FOR_OUTPUT','HTTPS homepage never printed','serviceKey='):
            self.assertNotIn(secret,text)
        for url in ('https://apis.data.go.kr/info','https://apis.data.go.kr/status'):
            selected=[params for target,params in calls if target==url]
            self.assertEqual(len(selected),1)
            self.assertEqual(selected[0],{'serviceKey':'TEST_SECRET%2B','pageNo':1,'numOfRows':10,'dataType':'JSON'})
        for section in diag.SECTIONS:self.assertIn('['+section+']',text)
        self.assertIn('E: Direct APIs succeeded',text)
        self.assertIn('ME_INFO_API: SUCCESS',text)
        self.assertIn('ME_STATUS_API: SUCCESS',text)

    def test_http_200_auth_and_parameter_errors_are_not_success(self):
        for code, expected in [('30','API_AUTH_ERROR'),('10','API_PARAMETER_ERROR'),('99','API_ERROR')]:
            report=diag.Report(self.settings)
            result=diag.api_probe(self.settings,'ME_URL',report,'ME Info API',lambda *a:self.response(code))
            self.assertEqual(result['outcome'],expected)

    def test_http_auth_status_and_parse_failure(self):
        for status, raw, expected in [(403,b'not JSON','API_AUTH_ERROR'),(502,b'not JSON','HTTP_ERROR'),
                                     (200,b'not JSON','RESPONSE_PARSE_ERROR'),(200,b'{}','RESPONSE_PARSE_ERROR')]:
            result=diag.api_probe(self.settings,'ME_URL',diag.Report(self.settings),'ME Info API',
                                  lambda *a:(status,'text/plain',raw))
            self.assertEqual(result['outcome'],expected)

    def test_xml_parsing_and_fields_only(self):
        raw=b'<response><header><resultCode>00</resultCode><resultMsg>OK</resultMsg></header><body><totalCount>1</totalCount><pageNo>1</pageNo><items><item><statId>NEVER_OUTPUT_ITEM_VALUE</statId></item></items></body></response>'
        report=diag.Report(self.settings)
        result=diag.api_probe(self.settings,'ME_STATUS_URL',report,'ME Status API',lambda *a:(200,'application/xml',raw))
        self.assertEqual(result['outcome'],'SUCCESS');self.assertNotIn('NEVER_OUTPUT_ITEM_VALUE',report.render())

    def test_exception_text_never_used_and_stages_distinct(self):
        ProxyError=type('ProxyError',(Exception,),{})
        cases=[(socket.gaierror('SECRET'),'DNS_ERROR'),(ssl.SSLError('SECRET'),'SSL_ERROR'),
               (TimeoutError('SECRET'),'TIMEOUT'),(ConnectionRefusedError('SECRET'),'CONNECTION_ERROR'),
               (ProxyError('SECRET'),'PROXY_ERROR'),(PermissionError('SECRET'),'NETWORK_PERMISSION_DENIED')]
        for error, expected in cases:self.assertEqual(diag.error_type(error),expected)
        self.assertEqual(diag.error_type(ConnectionRefusedError(),tcp=True),'TCP_CONNECTION_ERROR')
        with patch.object(diag.socket,'getaddrinfo',side_effect=PermissionError('SECRET')):
            self.assertEqual(diag.dns_probe('apis.data.go.kr'),'DNS_ERROR (PermissionError)')

    def test_no_credentials_sent_to_unapproved_or_query_urls(self):
        get=Mock()
        for url in ('https://evil.invalid/path','https://apis.data.go.kr/a?serviceKey=BAD',
                    'https://user:pass@apis.data.go.kr/a'):
            settings=Settings(dict(self.settings.values,ME_URL=url))
            self.assertEqual(diag.api_probe(settings,'ME_URL',diag.Report(settings),'ME Info API',get)['outcome'],'INVALID_URL')
        get.assert_not_called()

    def test_diagnosis_distinguishes_local_process_and_backend(self):
        dns={'apis.data.go.kr':'DNS_OK'};https={'tls_connected':True};ok={'outcome':'SUCCESS'}
        result,_=diag.diagnose(dns,https,ok,ok,{'chargers_http_status':200})
        self.assertTrue(any(x.startswith('F:') for x in result))
        result,_=diag.diagnose(dns,https,ok,ok,{'chargers_http_status':None})
        self.assertFalse(any(x.startswith('E:') for x in result))
        result,_=diag.diagnose(dns,https,ok,{'outcome':'API_PARAMETER_ERROR'}, {})
        self.assertTrue(any('different results' in x for x in result))
        self.assertFalse(any(x.startswith('F:') for x in result))

    def test_requests_params_and_loopback_proxy_bypass(self):
        response=Mock();response.status_code=200;response.headers={'Content-Type':'application/json; charset=utf-8'}
        response.iter_content.return_value=[b'{}'];response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        with patch('requests.get',return_value=response) as get:
            diag.http_get('https://apis.data.go.kr/info',{'serviceKey':'TEST_SECRET%2B'})
            self.assertEqual(get.call_args.kwargs['params'],{'serviceKey':'TEST_SECRET%2B'})
            self.assertFalse(get.call_args.kwargs['allow_redirects'])
            self.assertNotIn('proxies',get.call_args.kwargs)
            diag.http_get('http://127.0.0.1:8000/api/system/status')
            self.assertEqual(get.call_args.kwargs['proxies'],{'http':'','https':'','all':''})

    def test_echoed_auth_headers_and_proxy_values_never_written(self):
        report=diag.Report(self.settings)
        for value in ('Authorization: Bearer UNRELATED_SECRET', '"apiKey": "UNRELATED_SECRET"',
                      'Bearer UNRELATED_SECRET', 'https://user:UNRELATED_SECRET@proxy.invalid'):
            self.assertNotIn('UNRELATED_SECRET',report.safe(value))
        with patch.dict(diag.os.environ,{'HTTPS_PROXY':'https://user:UNRELATED_SECRET@proxy.invalid'}):
            with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()) as out:
                diag.run(Settings({}),lambda *a:(200,'application/json',b'{}'),lambda host:'DNS_OK',lambda:'SUCCESS',Path(tmp)/'report.txt')
            self.assertNotIn('UNRELATED_SECRET',out.getvalue())
            self.assertIn('HTTPS_PROXY: configured',out.getvalue())

if __name__=='__main__':unittest.main()
