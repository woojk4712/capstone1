"""Verify local read-only scenarios against actual stored observations. No external API calls."""
import hashlib
import json
import sqlite3
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
BASE = 'http://127.0.0.1:8000'


def fingerprint():
    uri = (ROOT/'data/runtime/external-api.sqlite').as_uri() + '?mode=ro'
    with sqlite3.connect(uri, uri=True) as db:
        rows = db.execute('SELECT stat_id,charger_id,body,collected_at FROM current_chargers ORDER BY stat_id,charger_id').fetchall()
        snapshots = db.execute('SELECT COUNT(*) FROM status_snapshots').fetchone()[0]
    return hashlib.sha256(json.dumps(rows,ensure_ascii=False).encode()).hexdigest(), snapshots


def read(path):
    r=requests.get(BASE+path,timeout=90)
    assert r.status_code==200, f'Local HTTP {r.status_code}'
    return r.json()


def check_result(result):
    before,after,delta=result['before'],result['after'],result['recoveredKw']
    for key,sign in [('normalKw',1),('stoppedKw',-1)]:
        if before[key] is not None:
            assert abs(after[key]-(before[key]+sign*delta))<1e-7
    assert before['maintenanceKw']==after['maintenanceKw']
    expected=delta/before['normalKw']*100 if before['normalKw'] else None
    assert result['recoveryRate']==expected


def main():
    replay=read('/api/system/status')['stale']
    ops=read('/api/operations/stations?stopped_only=true')
    overview=read('/api/analysis/overview?replay='+str(replay).lower())
    digest_before,snapshots_before=fingerprint()
    evidence={}
    for mode in ('hypothetical','simple'):
        if mode=='hypothetical':
            c=next(r for r in overview['potential'] if r['status'] in ('AVAILABLE','CHARGING'))
            endpoint='/api/analysis/simulate'
            payload={'chargerIds':[c['charger_id']],'hypothetical':True,'replay':replay}
        else:
            station=ops['items'][0]
            c=next(c for c in station['chargers'] if c['status']=='STOPPED' and (c['output_kw'] or 0)>0)
            endpoint='/api/operations/simulate'
            payload={'chargerIds':['ME:'+station['statId']+':'+str(c['chgerId'])],
                     'stationIds':[s['statId'] for s in ops['items']], 'replay':replay}
        r=requests.post(BASE+endpoint,json=payload,timeout=90)
        assert r.status_code==200, f'Local HTTP {r.status_code}'
        result=r.json()
        check_result(result)
        evidence[mode]={'before':result['before'],'after':result['after'],
                        'recoveredKw':result['recoveredKw'],'recoveryRate':result['recoveryRate'],
                        'replay':replay,'observationAt':result['observationAt']}
    digest_after,snapshots_after=fingerprint()
    evidence['originalRowsUnchanged']=digest_before==digest_after
    evidence['snapshotCountUnchanged']=snapshots_before==snapshots_after
    evidence['note']='Read-only requests only; concurrent collection may independently update observations.'
    (ROOT/'reports/scenario-storage-verification.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'originalRowsUnchanged':evidence['originalRowsUnchanged'],
                      'snapshotCountUnchanged':evidence['snapshotCountUnchanged'],
                      'hypotheticalRecoveredKw':evidence['hypothetical']['recoveredKw'],
                      'simpleRecoveredKw':evidence['simple']['recoveredKw']}))


if __name__=='__main__':
    main()
