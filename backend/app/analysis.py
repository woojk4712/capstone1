"""D1 source preparation and reviewed D1-D3 links. Never calls external APIs."""
import csv
import hashlib
import json
import math
import sqlite3
import unicodedata
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from pathlib import Path
from .settings import ROOT
from .storage import now
from .services.me_api import classifications, model, number

D1_FILENAME = '서울시 소유 전기차 충전소의 충전량(12월말까지).xlsx'
NS = {'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
HEADERS = ['날짜','충전소명','충전기 유형','충전량(kWh)']

def normalize_name(value):
    return ''.join(c for c in unicodedata.normalize('NFKC',str(value or '')).casefold() if c.isalnum())

def xlsx_rows(path):
    """Read the source's first worksheet without editing it or dropping duplicate rows."""
    with zipfile.ZipFile(path) as archive:
        strings=[]
        if 'xl/sharedStrings.xml' in archive.namelist():
            strings=[''.join(t.text or '' for t in item.findall('.//s:t',NS))
                     for item in ET.fromstring(archive.read('xl/sharedStrings.xml')).findall('s:si',NS)]
        workbook=ET.fromstring(archive.read('xl/workbook.xml'))
        sheet=workbook.find('s:sheets/s:sheet',NS)
        rid=sheet.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
        rels=ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
        target=next(r.get('Target') for r in rels if r.get('Id')==rid)
        target=target.lstrip('/') if target.startswith('/') else 'xl/'+target
        with archive.open(target) as stream:
            for _, element in ET.iterparse(stream,events=['end']):
                if element.tag!='{'+NS['s']+'}row': continue
                values={}
                for cell in element:
                    column=''.join(c for c in cell.get('r','') if c.isalpha())
                    index=0
                    for c in column:index=index*26+ord(c.upper())-64
                    value=cell.find('s:v',NS)
                    value=value.text if value is not None else ''.join(t.text or '' for t in cell.findall('.//s:t',NS))
                    if cell.get('t')=='s':value=strings[int(value)]
                    values[index-1]=value
                yield int(element.get('r')), [values.get(i,'') for i in range(max(values,default=-1)+1)]
                element.clear()

def source_date(value):
    try:return datetime.fromisoformat(str(value)).date()
    except ValueError:return (datetime(1899,12,30)+timedelta(days=float(value))).date()

class AnalysisService:
    def __init__(self, external, path=None):
        self.external=external
        self.path=Path(path or ROOT/'data/runtime/analysis.sqlite')
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.db() as db:
            db.executescript('''
              CREATE TABLE IF NOT EXISTS analysis_meta (name TEXT PRIMARY KEY, body TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS d1_demand (
                d1_station_name TEXT PRIMARY KEY, normalized_station_name TEXT NOT NULL,
                annual_fast_kwh REAL, monthly_fast_kwh TEXT NOT NULL, fast_row_count INTEGER NOT NULL);
              CREATE TABLE IF NOT EXISTS station_match (
                d1_station_name TEXT NOT NULL, d1_station_name_normalized TEXT NOT NULL,
                candidate_stat_id TEXT NOT NULL DEFAULT '', d3_station_name TEXT,
                d3_address TEXT, match_status TEXT NOT NULL CHECK(match_status IN ('confirmed','review','unmatched')),
                match_method TEXT NOT NULL, match_confidence REAL, review_note TEXT,
                reviewed_at TEXT, PRIMARY KEY(d1_station_name,candidate_stat_id));
              CREATE UNIQUE INDEX IF NOT EXISTS one_confirmed_d1 ON station_match(d1_station_name) WHERE match_status='confirmed';
              CREATE UNIQUE INDEX IF NOT EXISTS one_confirmed_d3 ON station_match(candidate_stat_id) WHERE match_status='confirmed';
            ''')

    @contextmanager
    def db(self):
        connection=sqlite3.connect(self.path,timeout=30)
        try:
            with connection:yield connection
        finally:connection.close()

    def meta(self,name):
        with self.db() as db:row=db.execute('SELECT body FROM analysis_meta WHERE name=?',(name,)).fetchone()
        return json.loads(row[0]) if row else {}

    def prepare_d1(self,path=None):
        path=Path(path) if path else ROOT/D1_FILENAME
        if not path.is_file():
            fallback=ROOT/'data/raw'/D1_FILENAME
            if not fallback.is_file():return {'available':False,'message':'D1 실제 충전량 원자료 필요'}
            path=fallback
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        original=self.meta('d1')
        if original.get('sha256')==digest:return original
        demand={};names=set();signatures=Counter();zeros=0;count=0;invalid=0;header=None
        folder=self.path.parent/'analysis';folder.mkdir(exist_ok=True)
        # A separate prepared CSV retains original columns, duplicates and zero rows.
        with (folder/'d1-preprocessed.csv').open('w',encoding='utf-8-sig',newline='') as file:
            writer=csv.writer(file)
            for rownum,values in xlsx_rows(path):
                if header is None:
                    if all(h in values for h in HEADERS):
                        header=values;writer.writerow(header+['normalized_station_name','source_row','in_2025','fast_record'])
                    continue
                if not any(v not in ('',None) for v in values):continue
                raw=dict(zip(header,values));name=raw.get('충전소명','');norm=normalize_name(name)
                count+=1;names.add(name);signatures[tuple(values)]+=1
                try:date=source_date(raw.get('날짜'))
                except (ValueError,TypeError,OverflowError):date=None
                in_year=date is not None and date.year==2025
                fast=str(raw.get('충전기 유형','')).strip()=='급속'
                writer.writerow(values+['']*(len(header)-len(values))+[norm,rownum,in_year,fast])
                try:
                    energy=Decimal(str(raw.get('충전량(kWh)')))
                    if not energy.is_finite():raise InvalidOperation()
                    if energy==0:zeros+=1
                except InvalidOperation:energy=None;invalid+=1
                if not in_year or not fast or not name:continue
                item=demand.setdefault(name,{'normalized_station_name':norm,'annual':Decimal(0),
                                             'months':[Decimal(0)]*12,'seen':set(),'rows':0,'invalid':False})
                item['rows']+=1;item['seen'].add(date.month)
                if energy is None:item['invalid']=True
                else:item['annual']+=energy;item['months'][date.month-1]+=energy
        if header is None:raise ValueError('D1 columns not found')
        metadata={'available':True,'path':str(path.resolve()),'columns':header,'sha256':digest,
                  'rows':count,'unique_station_names':len(names),'fast_station_names':len(demand),
                  'zero_rows':zeros,'duplicate_excess_rows':sum(n-1 for n in signatures.values()),
                  'invalid_energy_rows':invalid,'period':['2025-01-01','2025-12-31'],'prepared_at':now()}
        with self.db() as db:
            db.execute('DELETE FROM d1_demand')
            for name,item in demand.items():
                annual=None if item['invalid'] else float(item['annual'])
                monthly=[float(v) if i+1 in item['seen'] and not item['invalid'] else None for i,v in enumerate(item['months'])]
                db.execute('INSERT INTO d1_demand VALUES (?,?,?,?,?)',(name,item['normalized_station_name'],annual,json.dumps(monthly),item['rows']))
            if original:db.execute("UPDATE station_match SET match_status='review', review_note='D1 source changed; re-review required' WHERE match_status='confirmed'")
            db.execute('INSERT OR REPLACE INTO analysis_meta VALUES (?,?)',('d1',json.dumps(metadata,ensure_ascii=False)))
        return metadata

    def d3_stations(self):
        with self.external.storage.connection() as db:
            rows=db.execute('SELECT stat_id,body FROM current_chargers GROUP BY stat_id').fetchall()
        return [{'statId':sid,**{k:v for k,v in json.loads(body).items() if k in ('statNm','addr','lat','lng')}} for sid,body in rows]

    def prepare_matches(self):
        source=self.prepare_d1()
        if not source.get('available'):return source
        candidates=[(normalize_name(s.get('statNm')),s) for s in self.d3_stations()
                    if str(s.get('addr','')).startswith(('서울','서울특별시'))]
        with self.db() as db:
            demands=db.execute('SELECT d1_station_name,normalized_station_name FROM d1_demand').fetchall()
            db.execute("DELETE FROM station_match WHERE match_status!='confirmed'")
            confirmed={row[0] for row in db.execute("SELECT d1_station_name FROM station_match WHERE match_status='confirmed'")}
            for name,norm in demands:
                if name in confirmed:continue
                ranked=[]
                for d3norm,station in candidates:
                    ratio=1.0 if norm==d3norm else SequenceMatcher(None,norm,d3norm).ratio()
                    if ratio>=.55:ranked.append((ratio,station))
                ranked.sort(key=lambda r:(-r[0],r[1]['statId']))
                if not ranked:
                    db.execute('INSERT INTO station_match VALUES (?,?,?,?,?,?,?,?,?,?)',
                               (name,norm,'',None,None,'unmatched','candidate_search',None,'동일 시설 후보 없음; 주소·시설대장 필요',None))
                for score,station in ranked[:3]:
                    db.execute('INSERT INTO station_match VALUES (?,?,?,?,?,?,?,?,?,?)',
                               (name,norm,station['statId'],station.get('statNm'),station.get('addr'),'review',
                                'normalized_name' if score==1 else 'name_similarity',round(score,4),
                                '후보 점수이며 동일 시설 확률이 아님. D1 주소·좌표 부재; 시설대장/주소 등 독립 근거 확인 필요',None))
            db.execute('INSERT OR REPLACE INTO analysis_meta VALUES (?,?)',('matching',json.dumps({'generated_at':now(),'source_sha256':source['sha256']})))
        self.export_matches()
        return self.match_summary()

    def match_rows(self):
        with self.db() as db:
            db.row_factory=sqlite3.Row
            return [dict(row) for row in db.execute('SELECT * FROM station_match ORDER BY d1_station_name,match_confidence DESC')]

    def match_summary(self):
        grouped={}
        for row in self.match_rows():
            name=row['d1_station_name'];state=row['match_status']
            if name not in grouped or state=='confirmed' or state=='review' and grouped[name]=='unmatched':grouped[name]=state
        counts=Counter(grouped.values())
        return {name:counts[name] for name in ('confirmed','review','unmatched')}

    def export_matches(self):
        folder=self.path.parent/'analysis';folder.mkdir(exist_ok=True)
        rows=self.match_rows()
        columns=['d1_station_name','d1_station_name_normalized','candidate_stat_id','d3_station_name','d3_address',
                 'match_status','match_method','match_confidence','review_note','reviewed_at']
        with (folder/'station-match-review.csv').open('w',encoding='utf-8-sig',newline='') as file:
            writer=csv.DictWriter(file,fieldnames=columns);writer.writeheader();writer.writerows(rows)

    def confirm(self,name,stat_id,evidence):
        if len(evidence.strip())<12 or not any(word in evidence.casefold() for word in ('주소','시설대장','좌표','공식','운영기관','address','registry','coordinates')):
            raise ValueError('주소/시설대장 등 독립 검증 근거를 기록하세요')
        stations={s['statId']:s for s in self.d3_stations()}
        station=stations.get(stat_id)
        if not station or not str(station.get('addr','')).startswith('서울'):raise ValueError('서울시 D3 시설 확인 필요')
        with self.db() as db:
            if not db.execute('SELECT 1 FROM d1_demand WHERE d1_station_name=?',(name,)).fetchone():raise ValueError('D1 급속 기록 없는 시설')
            # Human-only operation; no similarity score can invoke this method.
            db.execute("DELETE FROM station_match WHERE d1_station_name=? AND match_status!='confirmed'",(name,))
            db.execute('''INSERT INTO station_match VALUES (?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(d1_station_name,candidate_stat_id) DO UPDATE SET
                match_status=excluded.match_status,match_method=excluded.match_method,
                review_note=excluded.review_note,reviewed_at=excluded.reviewed_at''',
                (name,normalize_name(name),stat_id,station.get('statNm'),station.get('addr'),'confirmed','manual_documented',None,evidence.strip(),now()))
        self.export_matches()

    def stations(self):
        types,states=classifications(self.external.settings);verified=bool(types and states)
        with self.db() as db:
            links=db.execute("SELECT m.d1_station_name,m.candidate_stat_id,d.annual_fast_kwh,d.monthly_fast_kwh FROM station_match m JOIN d1_demand d USING(d1_station_name) WHERE m.match_status='confirmed' AND d.fast_row_count>0").fetchall()
        items=[]
        for name,sid,annual,monthly in links:
            with self.external.storage.connection() as db:
                raw=db.execute('SELECT body,collected_at FROM current_chargers WHERE stat_id=?',(sid,)).fetchall()
            chargers=[model(json.loads(body),self.external.settings,stamp,self.external.is_fresh()) for body,stamp in raw]
            chargers=[c for c in chargers if c.get('delYn')=='N' and c['latitude'] is not None and c['longitude'] is not None]
            if not chargers:continue
            first=chargers[0]
            if not str(first.get('addr','')).startswith('서울'):continue
            fast=[c for c in chargers if str(c.get('chgerType')) in types] if verified else []
            def output(selected):
                if not verified or any(c['output_kw'] is None or c['output_kw']<=0 for c in selected):return None
                return sum(c['output_kw'] for c in selected)
            fresh=self.external.is_fresh()
            item={'analysisStationId':'ME:'+sid,'statId':sid,'statNm':first.get('statNm'), 'd1StationName':name,
                  'addr':first.get('addr'),'lat':first['latitude'],'lng':first['longitude'],
                  'annualFastKwh2025':annual,'monthlyFastKwh2025':json.loads(monthly),
                  'chargerCount':len(fast) if verified else None,'rawChargerCount':len(chargers),
                  'totalRatedOutputKw':output(fast),'availableRatedOutputKw':output([c for c in fast if c['status'] in ('AVAILABLE','CHARGING')]) if fresh else None,
                  'stoppedRatedOutputKw':output([c for c in fast if c['status']=='STOPPED']) if fresh else None,
                  'matchStatus':'confirmed','classificationVerified':verified,'chargers':fast if verified else chargers,
                  'statusCounts':{key:sum(c['status']==key for c in fast) if verified and fresh else None for key in ('AVAILABLE','CHARGING','STOPPED','MAINTENANCE','UNKNOWN','COMM_ERROR')}}
            if verified and not fast:continue
            items.append(item)
        source=self.meta('d1');summary=self.match_summary()
        return {'items':items,'total':len(items),'d1':source,'matching':summary,
                'apiConnected':self.external.status()['providers']['ME'].get('connected') is True and self.external.status()['providers']['ME'].get('error') is None,
                'rawDataAvailable':self.external.storage.charger_count()>0,'d1Available':source.get('available',False),
                'stationMatchingReady':bool(self.meta('matching')),'analysisDatasetReady':bool(items),
                'classificationVerified':verified,'rawChargerCount':self.external.storage.charger_count(),
                'last_success_at':self.external.storage.state('ME').get('last_success_at')}

    def alternatives(self,stat_id,radius=500,_origin=None):
        if radius not in (500,1000):raise ValueError('radius must be 500 or 1000')
        station=_origin or next((s for s in self.stations()['items'] if s['statId']==stat_id),None)
        if not station:raise ValueError('핵심 분석대상 시설 없음')
        types,states=classifications(self.external.settings)
        if not types or not states or not self.external.is_fresh():
            return {'items':[],'total':0,'totalRatedOutputKw':None,'status':'classification_required' if not types or not states else 'stale','message':'분류 검증 필요' if not types or not states else '최신 상태 확인 필요'}
        found=[]
        signature=self.external.storage.state('ME').get('last_success_at')
        if getattr(self,'_network_signature',None)!=signature or not hasattr(self,'_network_rows'):
            self._network_rows=self.external.storage.rows();self._network_signature=signature
        for raw,stamp in self._network_rows:
            if str(raw['statId'])==stat_id or raw.get('delYn')!='N' or raw.get('limitYn')!='N' or str(raw.get('chgerType')) not in types:continue
            if states.get(str(raw.get('stat'))) not in ('AVAILABLE','CHARGING'):continue
            row=model(raw,self.external.settings,stamp,True)
            if row['latitude'] is None or row['longitude'] is None:continue
            a,b=map(math.radians,(station['lat'],row['latitude']));dlat=b-a;dlon=math.radians(row['longitude']-station['lng'])
            distance=6371008.8*2*math.asin(math.sqrt(min(1.,math.sin(dlat/2)**2+math.cos(a)*math.cos(b)*math.sin(dlon/2)**2)))
            if distance<=radius:found.append(dict(row,distance_m=round(distance,1)))
        return {'items':sorted(found,key=lambda r:r['distance_m']),'total':len(found),'status':'ready',
                'totalRatedOutputKw':sum(r['output_kw'] for r in found) if all(r['output_kw'] is not None and r['output_kw']>0 for r in found) else None}

    def legacy_snapshot(self,radius=500):
        data=self.stations();stations=[]
        for source in data['items']:
            cs=[dict(c,id=source['analysisStationId']+':'+str(c['chgerId']),power_kw=c['output_kw'],
                     last_verified_at=c['collected_at'] if data['classificationVerified'] else None,ttl_minutes=15,
                     fast_verified=data['classificationVerified'],physical_verified=False,sharing_verified=False,
                     access_verified=c.get('limitYn')=='N',compatible_verified=False,
                     provider_alternative_eligible=data['classificationVerified'] and c.get('limitYn')=='N') for c in source['chargers']]
            stations.append(dict(id=source['analysisStationId'],name=source['statNm'],address=source['addr'],
                lat=source['lat'],lon=source['lng'],district=next((p for p in source['addr'].split() if p.endswith('구')),'미확인'),
                annual_kwh=source['annualFastKwh2025'],monthly_kwh=source['monthlyFastKwh2025'],chargers=cs,
                analysis_target=True,match_status='approved',quality_flags=[] if data['classificationVerified'] else ['분류 검증 필요']))
        # Keep the full network in storage; load only the union of nearby networks
        # into this analysis snapshot. They never become demand/KPI targets.
        network={};core_ids={s['id'] for s in stations};complete=data['classificationVerified']
        if data['classificationVerified']:
            for source in data['items']:
                result=self.alternatives(source['statId'],radius,source)
                if result['totalRatedOutputKw'] is None:complete=False
                for c in result['items']:
                    sid='ME:'+str(c['statId'])
                    if sid in core_ids:continue
                    s=network.setdefault(sid,dict(id=sid,name=c.get('statNm'),address=c.get('addr'),lat=c['latitude'],lon=c['longitude'],
                        district='대체망',chargers={},analysis_target=False,annual_kwh=None,monthly_kwh=None,quality_flags=[]))
                    s['chargers'][c['chgerId']]=dict(c,id=sid+':'+str(c['chgerId']),power_kw=c['output_kw'],last_verified_at=c['collected_at'],
                        ttl_minutes=15,fast_verified=True,provider_alternative_eligible=True)
            for s in network.values():s['chargers']=list(s['chargers'].values());stations.append(s)
        version=hashlib.sha256(json.dumps({'matches':self.match_rows(),'d1':self.meta('d1').get('sha256'),
                                           'classification':data['classificationVerified']},sort_keys=True).encode()).hexdigest()[:12]
        return {'id':'CORE:'+str(data['last_success_at'])+':'+version,
                'observed_at':data['last_success_at'] or now(),'stations':stations,'mode':'live',
                'provider_inventory':False,'network_complete':complete,'quality_flags':[]}
