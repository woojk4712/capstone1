"""Never log URLs, exceptions, headers, response bodies, or credentials."""
import errno
import json
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

MESSAGES = {
    'dns_error': 'DNS 이름 해석 실패',
    'ssl_error': 'SSL 인증서 또는 TLS 연결 오류',
    'timeout': '외부 서버 응답 시간 초과',
    'connection_refused': '외부 서버 연결 거부',
    'network_permission_denied': '실행 환경의 외부 네트워크 접근 권한 제한',
    'network_error': '외부 네트워크 연결 오류',
    'http_error': '외부 서버 HTTP 오류',
    'api_authentication_error': 'API 인증키 또는 활용승인 오류',
    'quota_exceeded': 'API 호출 한도 초과',
    'api_error': '제공기관 API 오류',
    'invalid_schema': '응답 스키마 검증 실패',
    'incomplete_collection': '페이지 누락 또는 수집 중 데이터 변경',
    'configuration_missing': '루트 .env의 필수 설정 누락',
    'invalid_url': '승인된 HTTPS API 주소 설정 필요',
    'schema_unverified': '한전 요청·응답 스키마 검증 대기',
    'not_collected': '데이터 미수집',
    'connection_error': '외부 서버 연결 오류',
    'parameter_error': '요청 파라미터 오류',
    'dependency_missing': 'requests 패키지 설치 필요',
}

class ProviderError(Exception):
    def __init__(self, kind, http_status=None):
        self.kind = kind
        self.http_status = http_status
        super().__init__(kind)

    def public(self):
        return {'kind': self.kind, 'message': MESSAGES.get(self.kind, '수집 오류'),
                'http_status': self.http_status}

def classify(error):
    reason = getattr(error, 'reason', error)
    if isinstance(reason, ssl.SSLError): kind = 'ssl_error'
    elif isinstance(reason, socket.gaierror): kind = 'dns_error'
    elif isinstance(reason, (TimeoutError, socket.timeout)): kind = 'timeout'
    elif isinstance(reason, ConnectionRefusedError) or getattr(reason, 'winerror', None) == 10061: kind = 'connection_refused'
    elif isinstance(reason, PermissionError) or getattr(reason, 'errno', None) in (errno.EACCES, errno.EPERM) or getattr(reason, 'winerror', None) in (5, 10013): kind = 'network_permission_denied'
    else: kind = 'network_error'
    return ProviderError(kind)

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # Never forward a service key to another host.

def request(url, params=None, timeout=15):
    try:
        parts = urllib.parse.urlsplit(url)
        if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password or parts.fragment:
            raise ProviderError('invalid_url')
        query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
        query = [(k, v) for k, v in query if k not in (params or {})]
        query.extend((params or {}).items())
        target = urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(query), ''))
        opener = urllib.request.build_opener(NoRedirect)
        try:
            response = opener.open(urllib.request.Request(target, headers={'Accept': 'application/json, application/xml, text/xml'}), timeout=timeout)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            status = response.code
            raw = response.read(16_000_001)
        if len(raw) > 16_000_000:
            raise ProviderError('invalid_schema', status)
        return status, raw
    except ProviderError:
        raise
    except (ValueError, UnicodeError):
        raise ProviderError('invalid_url') from None
    except (OSError, urllib.error.URLError) as error:
        raise classify(error) from None

def decode(raw):
    try:
        raw = raw.lstrip(b'\xef\xbb\xbf \r\n\t')
        if raw.startswith(b'<'):
            if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
                raise ProviderError('invalid_schema')
            root = ET.fromstring(raw)
            def convert(el):
                children = list(el)
                if not children:
                    return el.text or ''
                result = {}
                for child in children:
                    key = child.tag.split('}')[-1]
                    value = convert(child)
                    if key in result:
                        if not isinstance(result[key], list): result[key] = [result[key]]
                        result[key].append(value)
                    else: result[key] = value
                return result
            return {root.tag.split('}')[-1]: convert(root)}
        return json.loads(raw)
    except (ValueError, ET.ParseError, UnicodeError):
        raise ProviderError('invalid_schema') from None

def error_code(data):
    if isinstance(data, dict):
        for key, value in data.items():
            if key in ('resultCode', 'returnReasonCode'):
                return str(value)
            found = error_code(value)
            if found is not None: return found
    return None

def check_status(status, body=None):
    code = error_code(body)
    if status in (401, 403) or code in ('20', '30', '31'):
        raise ProviderError('api_authentication_error', status)
    if status == 429 or code in ('22', '23'):
        raise ProviderError('quota_exceeded', status)
    if status in (400, 422) or code in ('10', '11'):
        raise ProviderError('parameter_error', status)
    if not 200 <= status < 300:
        raise ProviderError('http_error', status)
    if code is not None and code not in ('00', '000', '0'):
        raise ProviderError('api_error', status)

def get_document(url, params, transport=request):
    status, raw = transport(url, params)
    try:
        body = decode(raw)
    except ProviderError:
        check_status(status)
        raise ProviderError('invalid_schema', status) from None
    check_status(status, body)
    return status, body

def classify_requests(error):
    """Inspect exception types, never stringify exceptions containing request URLs."""
    pending, seen = [error], set()
    names = set()
    while pending:
        item = pending.pop()
        if not isinstance(item, BaseException) or id(item) in seen: continue
        seen.add(id(item)); names.add(type(item).__name__)
        result = classify(item)
        if result.kind != 'network_error': return result
        pending.extend([getattr(item, 'reason', None), item.__cause__, item.__context__])
        pending.extend(a for a in item.args if isinstance(a, BaseException))
    if 'NameResolutionError' in names: return ProviderError('dns_error')
    if names & {'SSLError', 'CertificateError'}: return ProviderError('ssl_error')
    if any('Timeout' in name for name in names): return ProviderError('timeout')
    return ProviderError('connection_error')

def requests_response(url, params=None, timeout=20):
    try:
        import requests
    except ImportError:
        raise ProviderError('dependency_missing') from None
    try:
        parts = urllib.parse.urlsplit(url)
        if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password or parts.fragment:
            raise ProviderError('invalid_url')
        # requests handles parameter encoding; the key itself is never decoded,
        # interpolated into source URLs, printed, or forwarded by redirects.
        with requests.get(url, params=params or {}, timeout=timeout, allow_redirects=False, stream=True) as response:
            chunks, size = [], 0
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size > 16_000_000: raise ProviderError('invalid_schema', response.status_code)
                chunks.append(chunk)
            return response.status_code, response.headers.get('Content-Type', ''), b''.join(chunks)
    except ProviderError: raise
    except (ValueError, UnicodeError): raise ProviderError('invalid_url') from None
    except Exception as error:
        raise classify_requests(error) from None

def requests_transport(url, params=None, timeout=20):
    status, _, raw = requests_response(url, params, timeout)
    return status, raw
