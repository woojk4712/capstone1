"""No endpoint, authentication parameter, field, or status code is guessed.

To enable: review the approved provider documentation and store the explicit
KEPCO_CONTRACT JSON in the root .env. Unreviewed contracts never make a request.
"""
import json
from .transport import ProviderError, get_document, requests_transport
from .me_api import VALID_STATES

def at_path(body, path):
    for part in path.split('.'):
        if not isinstance(body, dict) or part not in body: raise ProviderError('invalid_schema')
        body = body[part]
    return body

class KEPCOAPI:
    def __init__(self, settings, transport=requests_transport):
        self.settings, self.transport = settings, transport
        self.http_status = None

    def fetch(self):
        key, url = self.settings.get('KEPCO_SERVICE_KEY'), self.settings.get('KEPCO_URL')
        if not key or not url: raise ProviderError('configuration_missing')
        try:
            c = json.loads(self.settings.get('KEPCO_CONTRACT', '{}'))
            required = ('key_param', 'items_path', 'id_field', 'status_field', 'source')
            if c.get('verified') is not True or any(not c.get(k) for k in required):
                raise ProviderError('schema_unverified')
            c.setdefault('status_map', {})
            if not isinstance(c['status_map'], dict) or not isinstance(c.get('params', {}), dict): raise ValueError()
            if any(v not in VALID_STATES for v in c['status_map'].values()): raise ValueError()
        except (ValueError, TypeError, AttributeError): raise ProviderError('schema_unverified') from None
        params = dict(c.get('params', {})); params[c['key_param']] = key
        self.http_status, body = get_document(url, params, self.transport)
        rows = at_path(body, c['items_path'])
        if not isinstance(rows, list): raise ProviderError('invalid_schema', self.http_status)
        result = []
        for row in rows:
            if not isinstance(row, dict) or c['id_field'] not in row or c['status_field'] not in row:
                raise ProviderError('invalid_schema', self.http_status)
            item = {'id': self.settings.redact(str(row[c['id_field']])),
                    'status': c['status_map'].get(str(row[c['status_field']]), 'UNKNOWN')}
            if c.get('updated_field') in row:
                item['api_updated_at'] = self.settings.redact(str(row[c['updated_field']]))
            result.append(item)
        return result
