"""Local API metadata only. Never prints credentials or response records."""
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import requests

ROOT=Path(__file__).resolve().parents[1]
BASE='http://127.0.0.1:8000'
PATHS=['/api/system/status','/api/chargers','/api/analysis/stations',
       '/api/analysis/overview?radius=500','/api/analysis/recovery-ranking',
       '/api/analysis/potential-impact','/api/operations/stations?stopped_only=true']


def probe(path):
    try:
        response=requests.get(BASE+path,timeout=120)
        data=response.json()
        row={'path':path,'http_status':response.status_code,'status':data.get('status'),
             'count':data.get('count',data.get('total')),'reason':data.get('reason'),
             'items_length':len(data['items']) if isinstance(data.get('items'),list) else None,
             'error':data.get('error_type')}
        if path=='/api/system/status':
            me=data.get('providers',{}).get('ME',{})
            row.update(connected=me.get('connected'),stale=data.get('stale'),
                       error=(me.get('current_error') or {}).get('kind'))
        if path=='/api/chargers':
            row.update(inventory_count=data.get('inventory_count'),unclassified_items_length=len(data.get('unclassified_items',[])))
        if path.startswith('/api/analysis/overview'):
            row.update(potential_length=len(data.get('potential',[])),recovery_length=len(data.get('priorities',[])),stale=data.get('stale'))
        if path=='/api/analysis/stations':
            sample=next((s for s in data.get('items',[]) if s.get('maintenance_analysis_status')=='READY'),None)
            row['_sample']=sample['statId'] if sample else None
        if '/maintenance/' in path:
            row.update(oneHour_length=len(data.get('oneHour',[])),twoHour_length=len(data.get('twoHour',[])),heatmap_rows=len(data.get('heatmap') or []))
        return row
    except (requests.RequestException,ValueError) as error:
        return {'path':path,'http_status':None,'status':'error','count':None,'reason':None,'items_length':None,'error':type(error).__name__}


def main():
    with ThreadPoolExecutor(max_workers=3) as pool:rows=list(pool.map(probe,PATHS))
    sample=next((row.pop('_sample') for row in rows if row.get('_sample')),None)
    if sample:rows.append(probe('/api/analysis/maintenance/'+sample))
    folder=ROOT/'reports'
    (folder/'analysis-api-final.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    table=['| Endpoint | HTTP | status | count | reason | items 길이 | 오류 |',
           '|---|---:|---|---:|---|---:|---|']
    for row in rows:
        table.append('| '+' | '.join(str(row.get(key)) if row.get(key) is not None else '—' for key in
            ('path','http_status','status','count','reason','items_length','error'))+' |')
    table+=['','—는 해당 필드가 없다는 의미이며 0건과 다릅니다.',
            '충전기 API의 eligible items와 원자료 unclassified_items 건수는 JSON에서 구분합니다.',
            '정비 API의 데이터는 items 대신 heatmap / oneHour / twoHour에 있습니다.']
    (folder/'analysis-api-final.md').write_text('\n'.join(table),encoding='utf-8')
    print(json.dumps(rows,ensure_ascii=True))


if __name__=='__main__':main()
