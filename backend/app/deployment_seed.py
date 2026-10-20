"""Static research inputs only. No observations, credentials, or matching decisions."""
import csv
import gzip
import hashlib
import json
from pathlib import Path
from .research import ResearchService
from .settings import ROOT

SEED_DIR = ROOT / 'data/seed'


def check_seed(folder=SEED_DIR):
    folder = Path(folder)
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    if manifest['format'] != 1:
        raise ValueError('unsupported_seed_format')
    path = folder / 'research.jsonl.gz'
    if hashlib.sha256(path.read_bytes()).hexdigest() != manifest['sha256']:
        raise ValueError('seed_checksum_mismatch')
    return manifest


class SeedResearchService(ResearchService):
    def __init__(self, external, path=None, seed_dir=SEED_DIR):
        super().__init__(external, path)
        manifest = check_seed(seed_dir)
        if self.meta('deployment_seed').get('sha256') != manifest['sha256']:
            self.restore(seed_dir, manifest)
        self.write_history()

    def restore(self, folder, manifest):
        counts = {'demand': 0, 'facility': 0, 'session': 0}
        # Single transaction: restart during restore cannot publish half a seed.
        with self.db() as db:
            for table in ('d1_demand', 'bridge_facilities', 'd2_sessions'):
                db.execute('DELETE FROM ' + table)
            with gzip.open(Path(folder) / 'research.jsonl.gz', 'rt', encoding='utf-8') as stream:
                for line in stream:
                    kind, row = json.loads(line)
                    if kind == 'meta':
                        db.execute('INSERT OR REPLACE INTO analysis_meta VALUES (?,?)', (row[0], json.dumps(row[1], ensure_ascii=False)))
                    elif kind == 'demand':
                        db.execute('INSERT INTO d1_demand VALUES (?,?,?,?,?)', row)
                    elif kind == 'facility':
                        db.execute('INSERT INTO bridge_facilities VALUES (?,?)', row)
                    elif kind == 'session':
                        # Algorithms read dates/flags; source energy and raw bodies
                        # intentionally remain outside the deployment seed.
                        db.execute('INSERT INTO d2_sessions VALUES (?,?,?,?,?,?,?,?)', (*row[:5], None, row[5], '{}'))
                    else:
                        raise ValueError('invalid_seed_record')
                    if kind in counts:
                        counts[kind] += 1
            if counts != manifest['counts']:
                raise ValueError('seed_row_count_mismatch')
            db.execute('INSERT OR REPLACE INTO analysis_meta VALUES (?,?)', ('deployment_seed', json.dumps({'sha256': manifest['sha256']})))

    def write_history(self):
        folder = self.path.parent / 'analysis'
        folder.mkdir(exist_ok=True)
        with (folder / 'd1-preprocessed.csv').open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(['충전소명', '충전기 유형', 'in_2025'])
            for name, types in self.meta('d1_types').items():
                for kind in types:
                    writer.writerow([name, kind, 'True'])

    def prepare_d1(self, path=None):
        return self.meta('d1')

    def read_bridge(self):
        with self.db() as db:
            facilities = {key: json.loads(body) for key, body in db.execute('SELECT id,body FROM bridge_facilities')}
        return facilities, self.meta('bridge')

    def prepare_d2(self):
        return self.meta('d2')
