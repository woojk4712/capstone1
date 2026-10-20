"""Verify attributed source files without API requests."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

if __name__ == '__main__':
    manifest = json.loads((ROOT / 'data/input/manifest.json').read_text(encoding='utf-8'))
    for entry in manifest['files']:
        path = ROOT / entry['path']
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
            raise SystemExit('Source file missing or changed: ' + entry['path'])
        print('OK: ' + entry['code'])
