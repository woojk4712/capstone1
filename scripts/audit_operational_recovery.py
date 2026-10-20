"""Read-only live API comparison. No external requests, credentials or raw rows in report."""
import argparse,hashlib,json,sqlite3
from pathlib import Path
import requests

ROOT=Path(__file__).resolve().parents[1]

def storage_digest():
    with sqlite3.connect('file:'+str(ROOT/'data/runtime/external-api.sqlite').replace('\\','/')+'?mode=ro',uri=True) as db:
        db.execute('BEGIN')
        state=json.loads(db.execute("SELECT body FROM provider_state WHERE provider='ME'").fetchone()[0])
        digest=hashlib.sha256()
        for row in db.execute('SELECT * FROM current_chargers ORDER BY stat_id,charger_id'):digest.update(repr(row).encode())
        snapshots=db.execute('SELECT COUNT(*),MAX(id) FROM status_snapshots').fetchone()
    return {'observationAt':state.get('last_success_at'),'currentRowsSha256':digest.hexdigest(),'snapshots':snapshots}

def main():
    p=argparse.ArgumentParser();p.add_argument('--base',default='http://127.0.0.1:8000');args=p.parse_args()
    assert args.base in ('http://127.0.0.1:8000','http://127.0.0.1:8774')
    session=requests.Session();calls=[]
    def get(path,**params):
        r=session.get(args.base+path,params=params,timeout=150);r.raise_for_status();calls.append({'path':path,'http':r.status_code});return r.json()
    initial=get('/api/operations/recovery');replay=initial['stale'];stamp=initial['observationAt']
    op=get('/api/operations/recovery',observationAt=stamp,replay=str(replay).lower())
    stations=get('/api/operations/stations',stopped_only='true',observationAt=stamp)
    assert stations['stoppedChargerCount']==op['count']
    assert stations['total']==op['stationCount']
    assert all(r['raw_stat']=='4' for r in op['items'])
    assert all(r['D'] is None or r['d1Connected'] for r in op['items'])
    assert all(r['operationalImpact'] is None or abs(r['operationalImpact']-(r['Q']+r['B'])/2)<1e-10 for r in op['items'])
    before=storage_digest();scenarios=[]
    eligible=[r for r in op['items'] if r['selectable']]
    for n in (1,3,5,10,len(eligible)):
        selected=eligible[:n]
        r=session.post(args.base+'/api/operations/simulate',json={'chargerIds':[r['charger_id'] for r in selected],
          'stationIds':[s['statId'] for s in op['stations']],'observationAt':stamp,'replay':replay},timeout=120)
        r.raise_for_status();d=r.json();assert d['observationAt']==stamp
        delta=sum(r['power_kw'] for r in selected);assert abs(d['recoveredKw']-delta)<1e-8
        assert abs(d['after']['normalKw']-d['before']['normalKw']-delta)<1e-8
        assert abs(d['before']['stoppedKw']-d['after']['stoppedKw']-delta)<1e-8
        assert d['after']['stoppedCount']==d['before']['stoppedCount']-len(selected)
        scenarios.append({'selected':len(selected),**d})
    after=storage_digest();unchanged=before==after
    assert unchanged or before['observationAt']!=after['observationAt'], 'Unexpected storage mutation without collector observation'
    sensitivity=[];reference=None
    for radius in (500,1000):
        for weight in ('equal','demand','power','alternative'):
            data=get('/api/analysis/overview',radius=radius,weight=weight,replay=str(replay).lower())
            ordered=[r['charger_id'] for r in data['potential']]
            if reference is None:reference=ordered
            positions={key:i for i,key in enumerate(reference)}
            sensitivity.append({'radius':radius,'weight':weight,'count':len(ordered),
              'observationAt':data['last_success_at'],'exact':sum(not r['scoreIsUpperBound'] for r in data['potential']),
              'upperBound':sum(r['scoreIsUpperBound'] for r in data['potential']),
              'changedPositions':sum(positions.get(key)!=i for i,key in enumerate(ordered)),
              'top10Overlap':len(set(reference[:10])&set(ordered[:10]))})
    quality=get('/api/analysis/quality')
    report={'base':args.base,'observationAt':stamp,'stale':replay,'counts':{'recovery':op['count'],'facilities':op['stationCount'],
      'simulationSelectable':op['selectableCount'],**op['diagnostics']},'matching':quality['matching'],
      'maintenance':quality['maintenanceReadyFacilities'],'sensitivity':sensitivity,'scenarios':scenarios,
      'storageBefore':before,'storageAfter':after,'storageUnchanged':unchanged,'calls':calls}
    (ROOT/'reports/operational-recovery-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('base','observationAt','stale','counts','matching','maintenance','storageUnchanged')},ensure_ascii=True))

if __name__=='__main__':main()
