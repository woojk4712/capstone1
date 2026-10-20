import json
import sqlite3
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime, timezone
from .settings import ROOT, runtime_directory

def now():
    return datetime.now(timezone.utc).isoformat()

class Storage:
    def __init__(self, path=None):
        self.path = str(path or runtime_directory() / 'external-api.sqlite')
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS status_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stat_id TEXT NOT NULL, charger_id TEXT NOT NULL,
                    status TEXT, output_kw REAL, api_updated_at TEXT,
                    collected_at TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS snapshot_station_time
                    ON status_snapshots(stat_id, charger_id, collected_at);
                CREATE TABLE IF NOT EXISTS current_chargers (
                    stat_id TEXT NOT NULL, charger_id TEXT NOT NULL,
                    body TEXT NOT NULL, collected_at TEXT NOT NULL,
                    PRIMARY KEY(stat_id, charger_id));
                CREATE TABLE IF NOT EXISTS provider_state (
                    provider TEXT PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS kepco_chargers (
                    id TEXT PRIMARY KEY, status TEXT NOT NULL,
                    api_updated_at TEXT, collected_at TEXT);
                CREATE TABLE IF NOT EXISTS charger_links (
                    stat_id TEXT, charger_id TEXT, kepco_id TEXT,
                    approved INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(stat_id, charger_id));
            ''')
            columns = {r[1] for r in db.execute('PRAGMA table_info(kepco_chargers)')}
            for column in ('api_updated_at', 'collected_at'):
                if column not in columns: db.execute(f'ALTER TABLE kepco_chargers ADD COLUMN {column} TEXT')

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=15)
        try:
            with db: yield db
        finally: db.close()

    def state(self, provider):
        with self.connection() as db:
            row = db.execute('SELECT body FROM provider_state WHERE provider=?', (provider,)).fetchone()
        return json.loads(row[0]) if row else dict(connected=False, last_success_at=None, count=0, error={'kind': 'not_collected', 'message': '데이터 미수집', 'http_status': None})

    def set_state(self, provider, state, db=None):
        if db is None:
            with self.connection() as connection: self.set_state(provider, state, connection)
        else:
            db.execute('INSERT INTO provider_state VALUES (?,?) ON CONFLICT(provider) DO UPDATE SET body=excluded.body', (provider, json.dumps(state, ensure_ascii=False)))

    def save_me(self, rows, timestamp, status):
        from .services.me_api import number
        with self.connection() as db:
            db.execute('DELETE FROM current_chargers')
            for row in rows:
                db.execute('INSERT INTO current_chargers VALUES (?,?,?,?)', (row['statId'], row['chgerId'], json.dumps(row, ensure_ascii=False), timestamp))
                db.execute('INSERT INTO status_snapshots (stat_id,charger_id,status,output_kw,api_updated_at,collected_at) VALUES (?,?,?,?,?,?)',
                           (row['statId'], row['chgerId'], row.get('stat'), number(row.get('output')), row.get('statUpdDt'), timestamp))
            old=db.execute('SELECT body FROM provider_state WHERE provider=?',('ME',)).fetchone()
            state=json.loads(old[0]) if old else {}
            state.update(connected=True,last_success_at=timestamp,last_attempt_at=state.get('last_attempt_at') or timestamp,
                         count=len(rows),http_status=status,error=None,current_error=None,stage='completed')
            self.set_state('ME',state,db)

    def save_kepco(self, rows, timestamp, status):
        with self.connection() as db:
            db.execute('DELETE FROM kepco_chargers')
            db.executemany('INSERT INTO kepco_chargers (id,status,api_updated_at,collected_at) VALUES (?,?,?,?)', [(r['id'], r['status'], r.get('api_updated_at'), timestamp) for r in rows])
            self.set_state('KEPCO', dict(connected=True, last_success_at=timestamp, last_attempt_at=timestamp, count=len(rows), http_status=status, error=None), db)

    def rows(self):
        with self.connection() as db:
            rows = db.execute('SELECT body,collected_at FROM current_chargers ORDER BY stat_id,charger_id').fetchall()
        return [(json.loads(body), stamp) for body, stamp in rows]

    def charger_count(self):
        with self.connection() as db:
            return db.execute('SELECT COUNT(*) FROM current_chargers').fetchone()[0]

    def comparison(self, stat_id):
        with self.connection() as db:
            return [{'charger_id': charger, 'secondary_status': status, 'api_updated_at': updated, 'collected_at': collected}
                    for charger, status, updated, collected in db.execute('''SELECT l.charger_id,k.status,k.api_updated_at,k.collected_at FROM charger_links l
                    JOIN kepco_chargers k ON l.kepco_id=k.id WHERE l.stat_id=? AND l.approved=1''', (stat_id,)).fetchall()]
