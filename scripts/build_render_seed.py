"""Create compact deployment inputs from public originals in isolated temp DBs."""
import csv
import gzip
import hashlib
import io
import json
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.settings import ROOT, Settings
from backend.app.storage import Storage
from backend.app.core import ExternalService
from backend.app.research import ResearchService, normalize_name


def build(folder):
    started = time.perf_counter()
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    counts = {'demand': 0, 'facility': 0, 'session': 0}
    with tempfile.TemporaryDirectory() as temp:
        external = ExternalService(Settings({}), Storage(Path(temp) / 'external.sqlite'))
        service = ResearchService(external, Path(temp) / 'analysis.sqlite')
        d1 = service.prepare_d1()
        facilities, bridge = service.read_bridge()
        d2 = service.prepare_d2()
        if not all(m.get('available') for m in (d1, bridge, d2)):
            raise ValueError('public_originals_required_to_build_seed')
        history = defaultdict(set)
        with (Path(temp) / 'analysis/d1-preprocessed.csv').open(encoding='utf-8-sig', newline='') as stream:
            for row in csv.DictReader(stream):
                if row.get('in_2025') == 'True':
                    history[normalize_name(row['충전소명'])].add(row['충전기 유형'].strip())
        metadata = {'d1': d1, 'bridge': bridge, 'd2': d2, 'd1_types': {n: sorted(t) for n,t in history.items()}}
        for name in ('d1', 'bridge', 'd2'):
            metadata[name]['path'] = Path(metadata[name]['path']).name
            metadata[name].pop('prepared_at', None)
        target = folder / 'research.jsonl.gz'
        with target.open('wb') as raw, gzip.GzipFile(fileobj=raw, mode='wb', mtime=0, filename='') as compressed, io.TextIOWrapper(compressed, encoding='utf-8') as stream:
            def emit(kind, row):
                stream.write(json.dumps([kind, row], ensure_ascii=False, separators=(',', ':')) + '\n')
                if kind in counts:
                    counts[kind] += 1
            for key, value in metadata.items():
                emit('meta', [key, value])
            with service.db() as db:
                for row in db.execute('SELECT * FROM d1_demand ORDER BY d1_station_name'):
                    emit('demand', row)
                for key, facility in sorted(facilities.items()):
                    # Official registry evidence; no ME snapshots or manual reviews.
                    emit('facility', [key, json.dumps(facility, ensure_ascii=False)])
                for row in db.execute('SELECT source_row,station_name,normalized_name,start_at,end_at,flags FROM d2_sessions ORDER BY source_row'):
                    emit('session', row)
        manifest = {'format': 1, 'sha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'bytes': target.stat().st_size,
                    'counts': counts, 'sources': {name: metadata[name]['sha256'] for name in ('d1','bridge','d2')},
                    'publisher': '서울특별시', 'license': '공공누리 제1유형: 출처표시',
                    'description': 'Derived demand, official facility evidence and session times/quality flags; no live snapshots or manual decisions.'}
        (folder / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'bytes': manifest['bytes'], 'counts': counts, 'elapsedSeconds': round(time.perf_counter()-started, 2)}))


if __name__ == '__main__':
    build(ROOT / 'data/seed')
