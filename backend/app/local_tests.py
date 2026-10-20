"""Local terminal diagnostics. No network access occurs on import."""
import json
from pathlib import Path
from .settings import Settings, ROOT, NAMES
from .services.transport import ProviderError, requests_response, decode, check_status
from .services.me_api import parse_page, FIELDS
from .services import me_api

def emit(settings, label, value):
    text = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    print(label + ': ' + settings.redact(text))

def failure(settings, error):
    labels = {'dns_error':'DNS error', 'ssl_error':'SSL error', 'timeout':'Timeout',
              'connection_error':'ConnectionError', 'connection_refused':'ConnectionError / connection refused',
              'network_permission_denied':'network permission denied in this execution environment',
              'http_error':'HTTP error', 'api_authentication_error':'인증키 오류',
              'parameter_error':'요청 parameter 오류', 'invalid_schema':'JSON/XML parsing 오류',
              'quota_exceeded':'API 호출 한도 초과', 'schema_unverified':'요청 명세 확인 필요',
              'configuration_missing':'루트 .env 필수 설정 누락', 'dependency_missing':'requests 설치 필요'}
    emit(settings, 'ERROR TYPE', labels.get(error.kind, error.kind))
    if error.http_status is not None: emit(settings, 'HTTP STATUS', error.http_status)
    return 1

def check_environment():
    settings = Settings.load()
    for name in NAMES:
        print(name + ': ' + ('configured' if settings.get(name) else 'missing'))
    return 0 if all(settings.presence().values()) else 1

def result_metadata(body):
    result = {}
    def walk(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in ('resultCode', 'resultMsg', 'totalCount', 'returnReasonCode', 'returnAuthMsg') and not isinstance(child, (dict, list)):
                    result[key] = child
                walk(child)
    walk(body)
    return result

def test_me(transport=requests_response, settings=None, evidence_path=None):
    settings = settings or Settings.load()
    if not settings.get('ME_URL') or not settings.get('ME_SERVICE_KEY'):
        return failure(settings, ProviderError('configuration_missing'))
    try:
        page = me_api.fetch_me_chargers(settings,transport)
        status = page.http_status
        emit(settings, 'HTTP STATUS', status)
        metadata = result_metadata(page.body)
        emit(settings, 'resultCode', metadata.get('resultCode', metadata.get('returnReasonCode', 'not provided')))
        emit(settings, 'resultMsg', metadata.get('resultMsg', metadata.get('returnAuthMsg', 'not provided')))
        rows, total = page.rows,page.total
        emit(settings, 'totalCount', total)
        emit(settings, 'item count', len(rows))
        fields = sorted(rows[0]) if rows else []
        emit(settings, 'first item field names', fields)
        # Evidence is structural only. Never save raw responses or item values.
        evidence = {'http_status':status, 'fields':fields, 'item_count':len(rows),
                    'required_fields_missing':[f for f in FIELDS if f not in fields],
                    'mapping_verified':False, 'validation_context':'user_local_terminal'}
        path = Path(evidence_path) if evidence_path else ROOT/'data/runtime/me-schema.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(settings.redact(json.dumps(evidence, ensure_ascii=False, indent=2)), encoding='utf-8')
        return 0
    except ProviderError as error: return failure(settings, error)
    except Exception:
        return failure(settings, ProviderError('invalid_schema'))

def read_kepco_request_contract(path=None):
    path = Path(path) if path else ROOT/'docs/kepco_request_contract.json'
    try:
        c = json.loads(path.read_text(encoding='utf-8-sig'))
        required = ('source', 'key_param', 'response_format', 'pagination')
        if c.get('request_verified') is not True or any(not c.get(k) for k in required):
            raise ProviderError('schema_unverified')
        if c['response_format'] not in ('JSON','XML','JSON/XML') or not isinstance(c.get('params'), dict):
            raise ProviderError('schema_unverified')
        if not isinstance(c.get('required_params'), list) or any(k not in c['params'] for k in c['required_params']):
            raise ProviderError('schema_unverified')
        if not isinstance(c['key_param'], str) or not c['key_param'].isidentifier():
            raise ProviderError('schema_unverified')
        return c
    except (OSError, ValueError, TypeError, AttributeError):
        raise ProviderError('schema_unverified') from None

def structure(body):
    arrays = []
    def walk(value, path=''):
        if isinstance(value, list):
            if not value or all(isinstance(item,dict) for item in value): arrays.append((path,value))
        elif isinstance(value, dict):
            for key, child in value.items(): walk(child, path+'.'+key if path else key)
    walk(body)
    return list(body) if isinstance(body,dict) else ['[]'] if isinstance(body,list) else [], arrays

def test_kepco(transport=requests_response, settings=None, contract_path=None, evidence_path=None):
    settings = settings or Settings.load()
    if not settings.get('KEPCO_URL') or not settings.get('KEPCO_SERVICE_KEY'):
        return failure(settings, ProviderError('configuration_missing'))
    try:
        # Request verification is separate from response field/status mapping.
        # Empty response mappings never prevent the first approved request.
        contract = read_kepco_request_contract(contract_path)
        params = dict(contract['params'])
        params[contract['key_param']] = settings.get('KEPCO_SERVICE_KEY')
        status, content_type, raw = transport(settings.get('KEPCO_URL'), params)
        emit(settings, 'HTTP STATUS', status); emit(settings, 'Content-Type', content_type)
        try: body = decode(raw)
        except ProviderError:
            check_status(status); raise ProviderError('invalid_schema', status) from None
        check_status(status, body)
        fmt = 'XML' if raw.lstrip(b'\xef\xbb\xbf \r\n\t').startswith(b'<') else 'JSON'
        top, arrays = structure(body)
        emit(settings, 'response format', fmt);emit(settings, 'top-level key/tag', top)
        selected = contract.get('items_path')
        candidates = [(path,rows) for path,rows in arrays if not selected or path==selected]
        # XML singleton item objects are an object until a reviewed items_path
        # explicitly identifies them. Never guess an arbitrary object is a row.
        if selected and not candidates:
            from .services.kepco_api import at_path
            value = at_path(body, selected)
            if isinstance(value,dict): candidates=[(selected,[value])]
            elif value in ('',None): candidates=[(selected,[])]
        emit(settings, 'data array key', [path for path,_ in candidates])
        emit(settings, 'first object field names', {path:sorted(rows[0]) if rows else [] for path,rows in candidates})
        emit(settings, 'returned count', {path:len(rows) for path,rows in candidates})
        evidence = {'http_status':status,'format':fmt,'top_level':top,
                    'arrays':{path:{'fields':sorted(rows[0]) if rows else [],'count':len(rows)} for path,rows in candidates},
                    'field_mapping_verified':False,'status_mapping_verified':False,
                    'validation_context':'user_local_terminal'}
        path=Path(evidence_path) if evidence_path else ROOT/'data/runtime/kepco-schema.json'
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(settings.redact(json.dumps(evidence,ensure_ascii=False,indent=2)),encoding='utf-8')
        return 0
    except ProviderError as error:
        if error.kind=='schema_unverified':
            print('확인 필요: 공식 매뉴얼의 인증 파라미터명, 필수 요청변수, 응답 형식, pagination')
            print('설정 파일: docs/kepco_request_contract.json (실제 응답·상태 매핑과 별도)')
        return failure(settings,error)
    except Exception:
        return failure(settings,ProviderError('invalid_schema'))
