import json, os, sqlite3, uuid
from datetime import datetime, timezone
from .config import DATA

def now(): return datetime.now(timezone.utc).isoformat()
class Store:
    def __init__(self,path=None):
        self.pg=bool(os.getenv('DATABASE_URL')) and path is None
        if self.pg:
            import psycopg
            self.db=psycopg.connect(os.environ['DATABASE_URL'],autocommit=True)
        else: self.db=sqlite3.connect(path or DATA/'ops.sqlite',check_same_thread=False)
        for t in ('snapshots','assets','matches','runs','simulations','collections','links'):
            self.execute(f'CREATE TABLE IF NOT EXISTS {t} (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, body TEXT NOT NULL)')
        self.db.commit()
        if self.pg:
            from .config import ROOT
            self.db.execute((ROOT/'infra'/'schema.sql').read_text(encoding='utf-8-sig'))
    def execute(self,sql,args=()): return self.db.execute(sql.replace('?','%s') if self.pg else sql,args)
    def put(self,t,body,key=None):
        key=key or str(uuid.uuid4())
        with (self.db.transaction() if self.pg else self.db):
            self.execute(f'INSERT INTO {t} VALUES (?,?,?) ON CONFLICT (id) DO UPDATE SET body=excluded.body',(key,now(),json.dumps(body,ensure_ascii=False)))
            if self.pg and t=='snapshots':
                for station in body.get('stations',[]):
                    lat,lon=station.get('lat'),station.get('lon')
                    if isinstance(lat,(int,float)) and isinstance(lon,(int,float)) and -90<=lat<=90 and -180<=lon<=180:
                        self.execute('INSERT INTO station_locations (snapshot_id,station_id,name,location) VALUES (?,?,?,ST_SetSRID(ST_MakePoint(?,?),4326)::geography) ON CONFLICT DO NOTHING',(key,station['id'],station['name'],lon,lat))
        return key
    def get(self,t,key):
        row=self.execute(f'SELECT body FROM {t} WHERE id=?',(key,)).fetchone()
        return json.loads(row[0]) if row else None
    def all(self,t): return [dict(json.loads(r[1]),_id=r[0]) for r in self.execute(f'SELECT id,body FROM {t} ORDER BY created_at DESC').fetchall()]
    def latest(self,t):
        rows=self.all(t)
        return rows[0] if rows else None
