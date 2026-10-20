"""Run ONLY from the user's ordinary Windows terminal. No calls on import.

This tool never starts/stops the server or changes data/mappings/.env.
Only allowlisted metadata is printed and saved; never exception/response text.
"""
import importlib.metadata
import json
import logging
import os
import platform
import re
import socket
import ssl
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from backend.app.settings import Settings, NAMES, read_env
from backend.app.services.transport import ProviderError, decode, check_status, classify_requests
from backend.app.services.me_api import parse_page
from backend.app.local_tests import result_metadata

ENV_PATH = ROOT / '.env'
REPORT_PATH = ROOT / 'reports/local-api-diagnosis.txt'
SECTIONS = ('Environment', 'DNS', 'TCP/HTTPS', 'ME Info API', 'ME Status API',
            'Proxy', 'FastAPI', 'Diagnosis', 'Recommended Next Action')
KINDS = {'dns_error':'DNS_ERROR', 'ssl_error':'SSL_ERROR', 'timeout':'TIMEOUT',
         'connection_error':'CONNECTION_ERROR', 'connection_refused':'CONNECTION_ERROR',
         'network_permission_denied':'NETWORK_PERMISSION_DENIED',
         'http_error':'HTTP_ERROR', 'api_authentication_error':'API_AUTH_ERROR',
         'parameter_error':'API_PARAMETER_ERROR', 'invalid_schema':'RESPONSE_PARSE_ERROR',
         'incomplete_collection':'RESPONSE_PARSE_ERROR', 'quota_exceeded':'API_QUOTA_ERROR',
         'api_error':'API_ERROR', 'configuration_missing':'CONFIGURATION_MISSING',
         'invalid_url':'INVALID_URL', 'dependency_missing':'DEPENDENCY_MISSING'}

def error_type(error, tcp=False):
    # Inspect types only. Exception strings frequently contain credential URLs.
    pending, seen = [error], set()
    while pending:
        current = pending.pop()
        if not isinstance(current, BaseException) or id(current) in seen:
            continue
        seen.add(id(current))
        if type(current).__name__ == 'ProxyError': return 'PROXY_ERROR'
        pending.extend([current.__cause__, current.__context__, getattr(current, 'reason', None)])
        pending.extend(x for x in current.args if isinstance(x, BaseException))
    if isinstance(error, ProviderError): kind = KINDS.get(error.kind, 'API_ERROR')
    elif isinstance(error, ssl.SSLError): kind = 'SSL_ERROR'
    else: kind = KINDS.get(classify_requests(error).kind, 'CONNECTION_ERROR')
    if tcp and kind == 'CONNECTION_ERROR': return 'TCP_CONNECTION_ERROR'
    return kind

class Report:
    def __init__(self, settings):
        self.settings = settings
        self.sections = {name: [] for name in SECTIONS}

    def safe(self, value):
        text = self.settings.redact(str(value))
        # Also remove arbitrary echoed URLs, credentials, and control characters.
        text = re.sub(r'https?://[^\s<>"\']+', '[URL OMITTED]', text, flags=re.I)
        text = re.sub(r'(?i)(?:proxy-authorization|authorization)["\']?\s*[:=].*', '[AUTH OMITTED]', text)
        text = re.sub(r'(?i)(?:servicekey|apikey|access_token|password)["\']?\s*[:=]\s*["\']?[^\s,"\';}]+', '[AUTH OMITTED]', text)
        text = re.sub(r'(?i)\bBearer\s+\S+', '[AUTH OMITTED]', text)
        text = ''.join(c if c.isprintable() else ' ' for c in text)
        return text[:2000]

    def add(self, section, label, value):
        if isinstance(value, (dict, list)): value = json.dumps(value, ensure_ascii=False)
        self.sections[section].append(self.safe(label) + ': ' + self.safe(value))

    def render(self):
        return '\n\n'.join('['+name+']\n'+'\n'.join(self.sections[name]) for name in SECTIONS)+'\n'

def dns_probe(host):
    try:
        socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        return 'DNS_OK'
    except Exception as error:
        # Never output an exception's message or arguments.
        return 'DNS_ERROR ('+type(error).__name__+')'

def tcp_probe():
    try:
        with socket.create_connection(('apis.data.go.kr', 443), timeout=8):
            return 'SUCCESS'
    except Exception as error:
        return error_type(error, tcp=True)

def http_get(url, params=None):
    """One requests.get call; no redirects/retries, no persisted response or URL."""
    try:
        import requests
    except ImportError:
        raise ProviderError('dependency_missing') from None
    # Loopback health checks must not be sent through an external proxy.
    options = {'proxies':{'http':'', 'https':'', 'all':''}} if urlsplit(url).hostname=='127.0.0.1' else {}
    with requests.get(url, params=params or {}, timeout=(8, 20),
                      allow_redirects=False, stream=True, **options) as response:
        raw = bytearray()
        for chunk in response.iter_content(65536):
            raw.extend(chunk)
            if len(raw) > 2_000_000:
                raise ProviderError('invalid_schema', response.status_code)
        # Only the media type is needed; never expose other response headers.
        media_type = response.headers.get('Content-Type', '').split(';')[0].strip()
        if not re.fullmatch(r'[\w.+-]+/[\w.+-]+', media_type): media_type = 'not provided'
        return response.status_code, media_type, bytes(raw)

def https_probe(host, get=http_get):
    try:
        status, _, _ = get('https://'+host)
        return {'outcome':'SUCCESS' if 200 <= status < 300 else 'HTTP_ERROR',
                'http_status':status, 'tls_connected':True}
    except Exception as error:
        return {'outcome':error_type(error), 'tls_connected':False}

def api_probe(settings, name, report, section, get=http_get):
    result = {'outcome':'CONFIGURATION_MISSING'}
    key, url = settings.get('ME_SERVICE_KEY'), settings.get(name)
    try:
        if not key or not url: raise ProviderError('configuration_missing')
        parts = urlsplit(url)
        if (parts.scheme != 'https' or parts.hostname != 'apis.data.go.kr'
                or parts.username or parts.password or parts.query or parts.fragment
                or parts.port not in (None, 443)):
            raise ProviderError('invalid_url')
        params = {'serviceKey':key, 'pageNo':1, 'numOfRows':10, 'dataType':'JSON'}
        status, media_type, raw = get(url, params)
        result['http_status'] = status
        report.add(section, 'HTTP STATUS', status)
        report.add(section, 'Content-Type', media_type)
        try: body = decode(raw)
        except ProviderError:
            check_status(status)
            raise ProviderError('invalid_schema', status) from None
        metadata = result_metadata(body)
        code = metadata.get('resultCode', metadata.get('returnReasonCode'))
        report.add(section, 'resultCode', code if code is not None else 'not provided')
        report.add(section, 'resultMsg', metadata.get('resultMsg', metadata.get('returnAuthMsg', 'not provided')))
        check_status(status, body)
        # Do not treat a 200 error document or an unrecognised response as success.
        if code is None: raise ProviderError('invalid_schema', status)
        rows, total, _ = parse_page(body, status)
        report.add(section, 'totalCount', total)
        report.add(section, 'item count', len(rows))
        report.add(section, 'first item field names', sorted(rows[0]) if rows else [])
        result['outcome'] = 'SUCCESS'
    except Exception as error:
        result['outcome'] = error_type(error)
    report.add(section, 'ME_INFO_API' if name=='ME_URL' else 'ME_STATUS_API', result['outcome'])
    return result

def server_probe(report, get=http_get):
    results = {}
    for endpoint in ('system/status', 'chargers'):
        label = '/api/'+endpoint
        try:
            status, _, raw = get('http://127.0.0.1:8000'+label)
            report.add('FastAPI', label+' HTTP STATUS', status)
            body = json.loads(raw)
            if not isinstance(body, dict): raise ValueError()
            if endpoint=='system/status':
                # No environment values, headers, raw errors, station data or tokens.
                runtime = body.get('runtime')
                report.add('FastAPI', 'runtime', runtime if runtime in ('fastapi','collector','preview') else 'unknown')
                enabled = body.get('collection_enabled')
                results['collection_enabled'] = enabled if isinstance(enabled, bool) else None
                report.add('FastAPI', 'collection_enabled', results['collection_enabled'])
                stamp = body.get('last_me_success_at')
                report.add('FastAPI', 'last_me_success_at', stamp if isinstance(stamp,str) and re.fullmatch(r'[0-9T:.+Z -]{1,50}',stamp) else 'none')
                count = body.get('stored_charger_count')
                report.add('FastAPI', 'stored_charger_count', count if type(count) is int else 'unknown')
                kind = body.get('recent_errors', {}).get('ME')
                known = set(KINDS) | {'not_collected','collection_in_progress'}
                results['recent_error'] = kind if kind in known or kind is None else 'unknown'
                report.add('FastAPI', 'recent_errors.ME', results['recent_error'])
            else:
                results['chargers_http_status'] = status
                if status==200:
                    items = body.get('items')
                    if not isinstance(items,list): raise ValueError()
                    report.add('FastAPI', 'returned item count', len(items))
                    # Existing API deliberately separates unverified classifications.
                    observed = body.get('unclassified_items')
                    if isinstance(observed,list): report.add('FastAPI', 'unclassified item count', len(observed))
                else:
                    kind = body.get('error_type')
                    report.add('FastAPI', 'error_type', kind if kind in set(KINDS)|{'not_collected','collection_in_progress'} else 'unknown')
        except Exception as error:
            kind = 'RESPONSE_PARSE_ERROR' if isinstance(error,(ValueError,TypeError,AttributeError)) else error_type(error)
            report.add('FastAPI', label, kind)
            if endpoint=='chargers': results['chargers_http_status'] = None
    return results

def diagnose(dns, https, info, status, server):
    findings, actions = [], []
    direct_ok = info['outcome']=='SUCCESS' and status['outcome']=='SUCCESS'
    if direct_ok:
        findings.append('A: Direct APIs succeeded in this terminal. If run in ordinary Windows PowerShell, the previous Agent network_permission_denied was an Agent/process restriction.')
        if server.get('chargers_http_status')==200:
            findings.append('F: Direct APIs and /api/chargers succeeded; ME live integration confirmed.')
            actions.append('Open http://127.0.0.1:8000/ and check the collected data.')
        elif server.get('chargers_http_status') is None:
            findings.append('Direct APIs succeeded; FastAPI server is unavailable. Backend integration is not yet confirmed.')
            actions.append('Run .\\run-local.cmd in ordinary Windows PowerShell, then run this diagnosis again.')
        else:
            findings.append('E: Direct APIs succeeded but /api/chargers failed; investigate the FastAPI process/configuration/collection path.')
            if server.get('collection_enabled') is False or server.get('recent_error')=='network_permission_denied':
                actions.append('Run .\\run-local.cmd in ordinary Windows PowerShell to replace the preview/restricted managed server, wait for collection, then diagnose again.')
            else:
                actions.append('Check recent_errors.ME and collection_enabled. A single-page direct test does not validate backend full pagination or collection completion.')
    else:
        if not dns['apis.data.go.kr'].startswith('DNS_OK'):
            findings.append('B: ME DNS resolution failed in this process; investigate Windows DNS/network configuration.')
            actions.append('Check the Windows internet connection, DNS configuration and VPN/security policy.')
        elif not https['tls_connected']:
            findings.append('C: DNS succeeded but HTTPS failed; investigate firewall/security software/TLS/proxy or process permissions.')
            actions.append('Review the TCP/HTTPS error types and proxy presence. Do not disable TLS verification or security software as a workaround.')
        for label, result in (('ME_INFO_API',info),('ME_STATUS_API',status)):
            outcome = result['outcome']
            if outcome=='SUCCESS': continue
            findings.append(label+': '+outcome)
            if outcome in ('API_AUTH_ERROR','API_PARAMETER_ERROR','API_ERROR','API_QUOTA_ERROR'):
                findings.append('D: An HTTP/API response was received; inspect portal approval/key type, request parameters or quota according to the reported category.')
                actions.append('Check the applicable public-data portal approval/manual; never share the key.')
            elif outcome=='RESPONSE_PARSE_ERROR':
                actions.append('Check the official response schema and whether a proxy returned a non-API page. Do not publish the raw response.')
            elif outcome in ('CONFIGURATION_MISSING','INVALID_URL'):
                actions.append('Check the root .env presence flags and HTTPS endpoint configuration; endpoint URLs must not contain a query or embedded credentials.')
            elif outcome=='NETWORK_PERMISSION_DENIED':
                actions.append('Run this tool in ordinary Windows PowerShell. If denial persists there, inspect local security/process network policy; do not attribute it solely to Agent sandbox.')
            else:
                actions.append('Use the stage-specific error type to check local connectivity/proxy/firewall and the upstream API service.')
        if info['outcome'] != status['outcome']:
            findings.append('Info and status endpoints have different results; full ME integration is not confirmed.')
    findings.append('Execution context is user-attested: Python cannot prove that its parent terminal is outside an Agent sandbox. KEPCO does not affect the ME diagnosis.')
    return findings, list(dict.fromkeys(actions))

def run(settings=None, get=http_get, dns=dns_probe, tcp=tcp_probe, report_path=REPORT_PATH):
    # Suppress third-party debug output and dotenv parser warnings (not our report).
    logging.disable(logging.CRITICAL)
    env_error = None
    if settings is None:
        try: settings = Settings(read_env(ENV_PATH))
        except Exception:
            settings = Settings({}); env_error = 'ENV_READ_ERROR'
    report = Report(settings)
    report.add('Environment','Python executable',sys.executable)
    report.add('Environment','Python version',platform.python_version())
    report.add('Environment','working directory',Path.cwd())
    report.add('Environment','.env absolute path',ENV_PATH)
    report.add('Environment','.env exists',ENV_PATH.is_file())
    report.add('Environment','project .venv',Path(sys.prefix).resolve()==(ROOT/'.venv').resolve())
    report.add('Environment','execution context','Run manually in ordinary Windows PowerShell; NOT verified automatically')
    if env_error: report.add('Environment','load result',env_error)
    for name in NAMES: report.add('Environment',name,'configured' if settings.get(name) else 'missing')
    for package in ('requests','fastapi'):
        try: version = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError: version = 'not installed'
        report.add('Environment',package+' version',version)
    report.add('Environment','collection_enabled setting','run-local.cmd default=true; explicit --preview/--no-collect=false; running value below')
    report.add('Environment','diagnostic collection_enabled','not applicable (one-shot test; no server/collector started)')
    resolved = {host:dns(host) for host in ('apis.data.go.kr','bigdata.kepco.co.kr')}
    for host, outcome in resolved.items(): report.add('DNS',host,outcome)
    report.add('TCP/HTTPS','apis.data.go.kr:443 TCP',tcp())
    https = https_probe('apis.data.go.kr',get)
    report.add('TCP/HTTPS','apis.data.go.kr HTTPS',https)
    report.add('TCP/HTTPS','bigdata.kepco.co.kr HTTPS (optional)',https_probe('bigdata.kepco.co.kr',get))
    info = api_probe(settings,'ME_URL',report,'ME Info API',get)
    status = api_probe(settings,'ME_STATUS_URL',report,'ME Status API',get)
    for name in ('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY'):
        report.add('Proxy',name,'configured' if os.environ.get(name) or os.environ.get(name.lower()) else 'not configured')
    report.add('Proxy','WinHTTP','diagnose-local.cmd runs netsh winhttp show proxy in console only; values not copied to this report')
    server = server_probe(report,get)
    findings, actions = diagnose(resolved,https,info,status,server)
    for finding in findings: report.add('Diagnosis','result',finding)
    for action in actions: report.add('Recommended Next Action','action',action)
    text = report.render()
    path = Path(report_path)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(text,encoding='utf-8')
    print(text,end='')
    return 0 if info['outcome']==status['outcome']=='SUCCESS' else 1

def main():
    try: return run()
    except KeyboardInterrupt:
        print('Diagnosis cancelled. No exception details printed.'); return 130
    except Exception:
        print('DIAGNOSTIC_TOOL_ERROR: report could not be completed. No exception details printed.'); return 2

if __name__=='__main__':
    sys.exit(main())
