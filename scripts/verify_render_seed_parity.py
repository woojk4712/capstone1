"""Optional local check against original public inputs; never reads live DBs."""
import csv
import hashlib
import json
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.core import ExternalService
from backend.app.settings import Settings
from backend.app.storage import Storage
from backend.app.research import ResearchService, normalize_name
from backend.app.deployment_seed import SeedResearchService


def fingerprint(service, query):
    digest = hashlib.sha256()
    with service.db() as db:
        for row in db.execute(query):
            digest.update(json.dumps(row, ensure_ascii=False, separators=(',', ':')).encode())
    return digest.hexdigest()


if __name__ == '__main__':
    with tempfile.TemporaryDirectory() as temp:
        folder = Path(temp)
        external = ExternalService(Settings({}), Storage(folder/'external.sqlite'))
        original = ResearchService(external, folder/'source/analysis.sqlite')
        original.prepare_d1()
        original.prepare_d2()
        start = time.perf_counter()
        seeded = SeedResearchService(external, folder/'seed/analysis.sqlite')
        print('Seed restore seconds:', round(time.perf_counter()-start, 3))
        for query in ('SELECT * FROM d1_demand ORDER BY d1_station_name',
                      'SELECT source_row,station_name,normalized_name,start_at,end_at,flags FROM d2_sessions ORDER BY source_row'):
            if fingerprint(original, query) != fingerprint(seeded, query):
                raise SystemExit('Seed parity FAIL')
        if original.read_bridge()[0] != seeded.read_bridge()[0]:
            raise SystemExit('Registry parity FAIL')
        history = defaultdict(set)
        with (folder/'source/analysis/d1-preprocessed.csv').open(encoding='utf-8-sig', newline='') as stream:
            for row in csv.DictReader(stream):
                if row['in_2025'] == 'True':
                    history[normalize_name(row['충전소명'])].add(row['충전기 유형'].strip())
        if {n: sorted(t) for n,t in history.items()} != seeded.meta('d1_types'):
            raise SystemExit('History parity FAIL')
        print('Source-to-seed demand/session/registry/history parity: PASS')
