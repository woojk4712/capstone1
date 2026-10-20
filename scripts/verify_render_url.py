"""Public read-only deployment smoke check; prints status, never response bodies."""
import argparse
import json
import urllib.request
import urllib.error
from urllib.parse import urlsplit

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('url')
    args = parser.parse_args()
    base = args.url.rstrip('/')
    if urlsplit(base).scheme != 'https' or urlsplit(base).query or urlsplit(base).username:
        raise SystemExit('Provide an HTTPS deployment origin without credentials/query parameters')
    paths = ('/', '/health', '/api/system/status', '/api/chargers', '/api/analysis/stations', '/api/deployment/status',
             '/apps/web/vendor/leaflet.js', '/apps/web/vendor/leaflet.css', '/apps/web/src/dashboard.js', '/apps/web/src/style.css')
    ready = True
    for path in paths:
        try:
            with urllib.request.urlopen(base+path, timeout=90) as response:
                status = response.status
                body = response.read()
            print(path, status)
            ready = ready and status == 200
            if path == '/api/system/status':
                data = json.loads(body)
                connected = bool(data['providers']['ME']['connected']) and not data['stale']
                print('ME fresh/connected:', connected)
                ready = ready and connected
            if path == '/api/deployment/status':
                data = json.loads(body)
                prepared = data['seedReady'] and data['phase'] == 'ready' and data['matching']['confirmed'] > 0
                print('Research prepared:', bool(prepared))
                ready = ready and prepared
        except urllib.error.HTTPError as error:
            print(path, error.code)
            ready = False
        except (OSError, ValueError, KeyError):
            print(path, 'check_failed')
            ready = False
    print('HTTP/data readiness:', 'PASS' if ready else 'NOT READY')
    print('Browser map/search/ranking/maintenance/simulation checks still required.')
    raise SystemExit(0 if ready else 1)
