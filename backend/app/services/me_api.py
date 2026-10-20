"""ME inventory adapter. Absent provider fields remain absent in the DTO.

Reference: https://www.data.go.kr/data/15076352/openapi.do (guide v1.25).
Numeric classification is enabled only with reviewed ME_* mapping settings.
"""
import hashlib
import json
import math
from urllib.parse import urlsplit
from dataclasses import dataclass
from .transport import ProviderError, get_document, requests_transport

FIELDS = ('statId', 'chgerId', 'statNm', 'addr', 'addrDetail', 'lat', 'lng', 'chgerType',
          'output', 'method', 'stat', 'statUpdDt', 'useTime', 'limitYn', 'limitDetail', 'delYn')
VALID_STATES = {'AVAILABLE', 'CHARGING', 'STOPPED', 'MAINTENANCE', 'COMM_ERROR', 'UNKNOWN'}

def number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None

def parse_page(body, status=200):
    try:
        r = body.get('response', body)
        b = r.get('body', r)
        rows = b.get('items', {})
        if isinstance(rows, dict): rows = rows.get('item', [])
        if rows in (None, ''): rows = []
        if isinstance(rows, dict): rows = [rows]
        total = int(b['totalCount'])
        page = int(b['pageNo'])
        if total < 0 or page < 1 or not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
            raise ValueError()
        return rows, total, page
    except (ValueError, TypeError, KeyError, AttributeError):
        raise ProviderError('invalid_schema', status) from None

@dataclass
class MEPage:
    rows: list
    total: int
    page: int
    http_status: int
    content_type: str
    body: dict

def fetch_me_chargers(settings, transport=None, page=1, size=10,
                      url_key='ME_URL', on_event=None, extra_params=None):
    """Single request/parsing implementation for local tests and FastAPI.

    Only the event name and counts cross the diagnostic callback boundary.
    Never pass a URL, key, provider message, response or exception to logging.
    """
    from .transport import requests_response, decode, check_status
    event = on_event or (lambda *args: None)
    key, url = settings.get('ME_SERVICE_KEY'), settings.get(url_key)
    if not key or not url: raise ProviderError('configuration_missing')
    try:
        parts = urlsplit(url)
        if (parts.scheme!='https' or parts.hostname!='apis.data.go.kr' or parts.username
                or parts.password or parts.fragment or parts.query or parts.port not in (None,443)):
            raise ProviderError('invalid_url')
    except ValueError: raise ProviderError('invalid_url') from None
    params = {'serviceKey':key,'pageNo':page,'numOfRows':size,'dataType':'JSON'}
    params.update(extra_params or {})
    event('request started')
    response = (transport or requests_response)(url, params)
    status, raw = response[0], response[-1]
    content_type = response[1] if len(response)==3 else ''
    event('HTTP response received')
    event('parsing started')
    try: body = decode(raw)
    except ProviderError:
        check_status(status)
        raise ProviderError('invalid_schema',status) from None
    check_status(status,body)
    rows, total, returned_page = parse_page(body,status)
    event('parsing completed')
    return MEPage(rows,total,returned_page,status,content_type,body)

class MEAPI:
    def __init__(self, settings, transport=requests_transport, on_event=None):
        self.settings, self.transport = settings, transport
        self.http_status = None
        self.on_event = on_event

    def page(self, page=1, size=9999):
        result = fetch_me_chargers(self.settings,self.transport,page,size,on_event=self.on_event,
                                   extra_params={'zcode':'11'})
        self.http_status = result.http_status
        return result.rows,result.total,result.page

    def fetch(self, max_pages=100):
        result, seen, hashes, total = [], set(), set(), None
        for page in range(1, max_pages + 1):
            rows, count, returned_page = self.page(page)
            if returned_page != page or (total is not None and count != total):
                raise ProviderError('incomplete_collection', self.http_status)
            total = count
            digest = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).digest()
            if rows and digest in hashes: raise ProviderError('incomplete_collection', self.http_status)
            hashes.add(digest)
            for row in rows:
                if not row.get('statId') or not row.get('chgerId'): raise ProviderError('invalid_schema', self.http_status)
                identifier = (row['statId'], row['chgerId'])
                if identifier in seen: raise ProviderError('incomplete_collection', self.http_status)
                seen.add(identifier)
                dto = {key: row[key] for key in FIELDS if key in row}
                # Provider echo protection applies even to approved data fields.
                dto = self.settings.scrub(dto)
                result.append(dto)
            if len(result) == total:
                return self.merge_status_updates(result) if self.settings.get('ME_STATUS_URL') else result
            if len(result) > total or not rows: raise ProviderError('incomplete_collection', self.http_status)
        raise ProviderError('incomplete_collection', self.http_status)

    def merge_status_updates(self, inventory, max_pages=100):
        url = self.settings.get('ME_STATUS_URL')
        if urlsplit(url).hostname != 'apis.data.go.kr': raise ProviderError('invalid_url')
        lookup = {(str(r['statId']), str(r['chgerId'])): r for r in inventory}
        expected, received, seen = None, 0, set()
        for page in range(1, max_pages + 1):
            result = fetch_me_chargers(self.settings,self.transport,page,9999,'ME_STATUS_URL',self.on_event,
                                       {'zcode':'11','period':5})
            status = result.http_status
            updates, total, returned = result.rows,result.total,result.page
            if returned != page or expected is not None and total != expected:
                raise ProviderError('incomplete_collection', status)
            expected = total
            for update in updates:
                if not update.get('statId') or not update.get('chgerId'): raise ProviderError('invalid_schema', status)
                identifier = (str(update['statId']), str(update['chgerId']))
                if identifier in seen: raise ProviderError('incomplete_collection', status)
                seen.add(identifier)
                if identifier in lookup:
                    for field in ('stat', 'statUpdDt'):
                        if field in update:
                            value = update[field]
                            lookup[identifier][field] = self.settings.redact(value) if isinstance(value, str) else value
            received += len(updates)
            if received == total: return inventory
            if received > total or not updates: raise ProviderError('incomplete_collection', status)
        raise ProviderError('incomplete_collection', self.http_status)

def classifications(settings):
    contract = settings.me_contract
    if contract.get('status_verified') is True:
        states = contract.get('status_map', {})
        types = contract.get('fast_types', []) if contract.get('charger_type_verified') is True else []
        if isinstance(states, dict) and all(v in VALID_STATES for v in states.values()):
            return set(map(str, types)), states
    try:
        verified = settings.get('ME_MAPPING_VERIFIED').lower() == 'true'
        types = json.loads(settings.get('ME_FAST_TYPES', '[]') or '[]')
        states = json.loads(settings.get('ME_STATUS_MAP', '{}') or '{}')
        if not isinstance(types, list) or not isinstance(states, dict): raise ValueError()
        if any(v not in VALID_STATES for v in states.values()): raise ValueError()
        return (set(map(str, types)), states) if verified else (set(), {})
    except (ValueError, TypeError):
        return set(), {}

def model(row, settings, collected_at, fresh=True):
    types, states = classifications(settings)
    result = dict(row)
    power, lat, lng = number(row.get('output')), number(row.get('lat')), number(row.get('lng'))
    coordinates = lat is not None and lng is not None and -90 <= lat <= 90 and -180 <= lng <= 180 and (lat, lng) != (0, 0)
    state = states.get(str(row.get('stat')), 'UNKNOWN') if fresh else 'UNKNOWN'
    eligible = (str(row.get('chgerType')) in types and power is not None and power > 0
                and coordinates and row.get('delYn') == 'N' and row.get('limitYn') == 'N')
    result.update(status=state, output_kw=power, latitude=lat if coordinates else None,
                  longitude=lng if coordinates else None, collected_at=collected_at,
                  analysis_eligible=eligible, classification_verified=bool(types and states))
    result.update(statusClassificationVerified=bool(states), chargerTypeClassificationVerified=bool(types))
    if settings.me_contract.get('status_verified') is True:
        from .me_classification import STATUS_LABELS, TYPE_LABELS
        result.update(status_label=STATUS_LABELS.get(str(row.get('stat')), '상태미확인') if fresh else '최신 상태 확인 필요',
                      type_label=TYPE_LABELS.get(str(row.get('chgerType')), '미확인 유형'),
                      charging_speed='SLOW' if str(row.get('chgerType')) in settings.me_contract.get('slow_types', []) else 'UNKNOWN',
                      recovery_review_candidate=fresh and state=='STOPPED' and row.get('delYn')=='N')
    return result
