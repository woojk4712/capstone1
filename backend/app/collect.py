"""Safe metadata only; no request URLs, response bodies, or credentials."""
import argparse
import json
from .core import ExternalService

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--diagnose', action='store_true')
    args = parser.parse_args()
    service = ExternalService()
    if args.diagnose:
        result = {'environment': service.settings.presence(), 'network': service.diagnose()}
    else:
        service.refresh()
        result = service.status()
    print(json.dumps(result, ensure_ascii=False))

if __name__ == '__main__': main()
