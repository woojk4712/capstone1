"""Official local D1 -> OA-21712 -> ME linkage and research algorithms.

No external requests; no mutation of source files or ME observations.
"""
import copy
import csv
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from bisect import bisect_right
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from .analysis import AnalysisService, normalize_name, xlsx_rows, ROOT
from .storage import now
from .services.me_api import model, number, classifications
from .facility_matching import address_key, physical_address, bridge_candidates, station_address_index

BRIDGE='서울시 소유 전기차 충전소 정보.csv'
D2='서울시 소유 전기차충전기 일별 시간별 충전현황(2025년).xlsx'
CONFIRMED=('confirmed','confirmed_auto','confirmed_manual')
WEIGHTS={'equal':(1/3,1/3,1/3),'demand':(.5,.25,.25),'power':(.25,.5,.25),'alternative':(.25,.25,.5)}

def charger_key(value):
    value=str(value or '').strip()
    return str(int(value)) if re.fullmatch(r'\d+',value) else value

def bridge_speed(row):
    text=str(row.get('CHARG_TYPE',''))+' '+str(row.get('CHARG_CPCT',''))
    fast='급속' in text;slow='완속' in text
    return 'CONFLICT' if fast and slow else 'FAST' if fast else 'SLOW' if slow else 'UNKNOWN'

def distance(a,b):
    x,y=map(math.radians,(a['lat'],b['lat']));dl=math.radians(b['lng']-a['lng'])
    return 6371008.8*2*math.asin(math.sqrt(min(1,math.sin((y-x)/2)**2+math.cos(x)*math.cos(y)*math.sin(dl/2)**2)))

def average_ranks(values):
    ordered=sorted(values.items(),key=lambda p:p[1]);n=len(ordered);out={};i=0
    while i<n:
        j=i+1
        while j<n and ordered[j][1]==ordered[i][1]:j+=1
        score=((i+j-1)/2)/(n-1) if n>1 else .5
        for key,_ in ordered[i:j]:out[key]=score
        i=j
    return out

class ResearchService(AnalysisService):
    def __init__(self,external,path=None):
        super().__init__(external,path)
        with self.db() as db:
            schema=db.execute("SELECT sql FROM sqlite_master WHERE name='station_match'").fetchone()[0]
            if 'confirmed_auto' not in schema:
                db.execute('DROP INDEX IF EXISTS one_confirmed_d1');db.execute('DROP INDEX IF EXISTS one_confirmed_d3')
                db.execute('ALTER TABLE station_match RENAME TO station_match_old')
                db.execute(schema.replace("('confirmed','review','unmatched')","('confirmed','confirmed_auto','confirmed_manual','review','unmatched')"))
                db.execute('INSERT INTO station_match SELECT * FROM station_match_old');db.execute('DROP TABLE station_match_old')
            db.executescript('''
              CREATE UNIQUE INDEX IF NOT EXISTS one_confirmed_d1 ON station_match(d1_station_name) WHERE match_status IN ('confirmed','confirmed_auto','confirmed_manual');
              CREATE UNIQUE INDEX IF NOT EXISTS one_confirmed_d3 ON station_match(candidate_stat_id) WHERE match_status IN ('confirmed','confirmed_auto','confirmed_manual');
              CREATE TABLE IF NOT EXISTS bridge_facilities (id TEXT PRIMARY KEY,body TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS match_evidence (d1_name TEXT,stat_id TEXT,body TEXT NOT NULL,PRIMARY KEY(d1_name,stat_id));
              CREATE TABLE IF NOT EXISTS bridge_d3 (bridge_id TEXT,stat_id TEXT,body TEXT NOT NULL,PRIMARY KEY(bridge_id,stat_id));
              CREATE TABLE IF NOT EXISTS d2_sessions (source_row INTEGER PRIMARY KEY,station_name TEXT,normalized_name TEXT,start_at TEXT,end_at TEXT,raw_energy TEXT,flags TEXT,raw_body TEXT);
              CREATE INDEX IF NOT EXISTS d2_name ON d2_sessions(normalized_name);
            ''')

    def find_source(self,filename):
        for p in (ROOT/filename,ROOT/'data/input'/filename):
            if p.is_file():return p
        return None

    def read_bridge(self):
        path=self.find_source(BRIDGE)
        if not path:return {},{'available':False,'needed':'data/input/'+BRIDGE}
        fields={'OPER_INST':'운영기관','CHARG_STTN':'충전소','CHARG_ID':'충전기ID','CHARG_TYPE':'충전기타입','ADDR':'주소','SGG':'시군구','CHARG_CPCT':'충전용량','USE_PSBLTY_TM':'이용가능시간','USER_LMT':'이용자 제한'}
        for encoding in ('utf-8-sig','cp949','utf-16'):
            try:
                with path.open(encoding=encoding,newline='') as f:raw=list(csv.DictReader(f))
                break
            except UnicodeError:continue
        else:raise ValueError('시설대장 인코딩 확인 필요')
        facilities={}
        for original in raw:
            row={key:original.get(key,original.get(label,'')) for key,label in fields.items()}
            row['original']=original
            name=normalize_name(row['CHARG_STTN']);addr=address_key(row['ADDR'])
            if not name or not addr:continue
            full_addr=normalize_name(str(row['ADDR']).replace('서울시','서울특별시'))
            key=hashlib.sha256((name+'|'+full_addr).encode()).hexdigest()[:20]
            facility=facilities.setdefault(key,{'id':key,'name':row['CHARG_STTN'],'address':row['ADDR'],'normalized_name':name,'normalized_address':addr,'full_address_normalized':full_addr,'district':row['SGG'].strip(),'rows':[]})
            facility['rows'].append(row)
        units=[r for f in facilities.values() for r in f['rows']]
        return facilities,{'available':True,'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'encoding':encoding,'rows':len(raw),'facilities':len(facilities),'columns':list(raw[0]) if raw else [],'speedEvidenceCounts':dict(Counter(bridge_speed(r) for r in units))}

    def prepare_all(self):
        source=self.prepare_d1();facilities,metadata=self.read_bridge();d3=self.d3_stations()
        history=defaultdict(set)
        prepared=self.path.parent/'analysis/d1-preprocessed.csv'
        if prepared.exists():
            with prepared.open(encoding='utf-8-sig',newline='') as f:
                for row in csv.DictReader(f):
                    if row.get('in_2025')=='True':history[normalize_name(row.get('충전소명'))].add(str(row.get('충전기 유형','')).strip())
        # Only official exact name AND independent physical address, unique both ways.
        boundaries=defaultdict(set);positions=defaultdict(list);local_ids=defaultdict(list);raw_groups=defaultdict(list)
        for row,_ in self.external.storage.rows():
            sid=str(row['statId'])
            raw_groups[sid].append(row)
            boundaries[sid].add((normalize_name(row.get('statNm')),address_key(row.get('addr'))))
            local_ids[sid].append(charger_key(row.get('chgerId')))
            lat,lng=number(row.get('lat')),number(row.get('lng'))
            if lat is not None and lng is not None and -90<=lat<=90 and -180<=lng<=180 and (lat,lng)!=(0,0):positions[sid].append({'lat':lat,'lng':lng})
        bridge_links={};bridge_methods={};bridge_holds={};reverse=Counter();address_index=station_address_index(d3)
        for key,f in facilities.items():
            candidates,method=bridge_candidates(f,d3,address_index)
            ids=defaultdict(set)
            for row in f['rows']:ids[charger_key(row['CHARG_ID'])].add((row['CHARG_TYPE'],row['CHARG_CPCT']))
            hold=method
            if len(candidates)==1:
                station=candidates[0];sid=station['statId'];points=positions[sid]
                if len(boundaries[sid])!=1:hold='d3_boundary_conflict'
                elif not all(k and len(v)==1 for k,v in ids.items()):hold='registry_charger_id_conflict'
                elif len(local_ids[sid])!=len(set(local_ids[sid])):hold='d3_local_charger_id_conflict'
                elif not points or any(distance(points[0],p)>150 for p in points):hold='coordinate_conflict'
                else:
                    bridge_links[key]=station;bridge_methods[key]=method;reverse[sid]+=1;hold=''
            bridge_holds[key]=hold
        bridge_links={k:v for k,v in bridge_links.items() if reverse[v['statId']]==1}
        for key,f in facilities.items():
            if key in bridge_methods and key not in bridge_links:bridge_holds[key]='multiple_registry_facilities_for_d3'
        with self.db() as db:
            db.execute('DELETE FROM bridge_facilities');db.execute('DELETE FROM bridge_d3')
            for key,f in facilities.items():db.execute('INSERT INTO bridge_facilities VALUES (?,?)',(key,json.dumps(f,ensure_ascii=False)))
            for key,station in bridge_links.items():
                db.execute('INSERT INTO bridge_d3 VALUES (?,?,?)',(key,station['statId'],json.dumps({'evidence':'OA-21712 physical address + unique D3 statId + consistent facility boundary','method':bridge_methods[key],'facility':facilities[key]},ensure_ascii=False)))
            demands=db.execute('SELECT * FROM d1_demand').fetchall()
            manual={r[0] for r in db.execute("SELECT d1_station_name FROM station_match WHERE match_status IN ('confirmed','confirmed_manual')")}
            manual_holds={(r[0],r[1]):r[2] for r in db.execute("SELECT d1_station_name,candidate_stat_id,review_note FROM station_match WHERE match_status='review' AND match_method='manual_documented'")}
            db.execute("DELETE FROM station_match WHERE match_status NOT IN ('confirmed','confirmed_manual')")
            db.execute("DELETE FROM match_evidence WHERE d1_name NOT IN (SELECT d1_station_name FROM station_match)")
            proposals=[]
            for name,norm,energy,months,count in demands:
                if name in manual:continue
                exact=[f for f in facilities.values() if f['normalized_name']==norm]
                ranked=exact or sorted((f for f in facilities.values() if SequenceMatcher(None,norm,f['normalized_name']).ratio()>=.65),key=lambda f:-SequenceMatcher(None,norm,f['normalized_name']).ratio())[:3]
                auto=len(exact)==1 and exact[0]['id'] in bridge_links
                if auto:
                    f=exact[0];station=bridge_links[f['id']]
                    proposals.append((name,norm,station,f,True,1.0))
                else:
                    candidates=[]
                    for f in ranked:
                        candidates.extend((station,f) for station in d3 if normalize_name(station.get('statNm'))==f['normalized_name'] or address_key(station.get('addr'))==f['normalized_address'])
                    if not candidates:
                        # Name-only candidates remain review, never final.
                        candidates=[(station,ranked[0] if ranked else None) for station in d3 if normalize_name(station.get('statNm'))==norm]
                    if candidates:
                        seen=set()
                        for station,f in candidates[:10]:
                            if station['statId'] in seen:continue
                            seen.add(station['statId']);score=SequenceMatcher(None,norm,normalize_name(station.get('statNm'))).ratio()
                            proposals.append((name,norm,station,f,False,score))
                    else:proposals.append((name,norm,None,ranked[0] if ranked else None,False,None))
            auto_ids=Counter(s['statId'] for _,_,s,_,auto,_ in proposals if auto)
            used={r[0] for r in db.execute("SELECT candidate_stat_id FROM station_match WHERE match_status IN ('confirmed','confirmed_manual')")}
            for name,norm,station,f,auto,score in proposals:
                sid=station['statId'] if station else ''
                auto=auto and auto_ids[sid]==1 and sid not in used
                if (name,sid) in manual_holds:auto=False
                status='confirmed_auto' if auto else 'review' if station or f else 'unmatched'
                evidence=('D1 exact normalized OA-21712 station name + '+('exact D3 station name + ' if bridge_methods[f['id']]=='exact_registry_name_and_physical_address' else '')+'exact physical '+physical_address(f['address'])['kind']+' address + unique D3 statId + consistent coordinates/boundary') if auto else ''
                exact_facilities=[v for v in facilities.values() if v['normalized_name']==norm]
                hold_code='' if auto else 'no_official_registry_name_match' if not exact_facilities else 'multiple_registry_addresses_for_d1' if len(exact_facilities)>1 else bridge_holds.get(exact_facilities[0]['id']) or 'd1_d3_confirmation_conflict'
                reason='' if auto else hold_code+' · 명칭 유사도 및 시설 내 순번 ID만으로 자동확정하지 않음'
                if (name,sid) in manual_holds:reason=manual_holds[(name,sid)];hold_code='manual_hold'
                details={'bridge':f,'evidence':evidence,'match_evidence':evidence,'confidence_reason':('Independent official name/address, unique facility and coordinates. Local ordinal charger IDs are not global identity proof.' if auto else reason),'hold_reason':reason,'hold_reason_code':hold_code,'d3_station_name_normalized':normalize_name(station.get('statNm')) if station else None,'d3_address_normalized':address_key(station.get('addr')) if station else None,'annualFastKwh2025':next((r[2] for r in demands if r[0]==name),None),'lat':number(station.get('lat')) if station else None,'lng':number(station.get('lng')) if station else None,'d3_chargers':raw_groups.get(sid,[])}
                db.execute('INSERT INTO station_match VALUES (?,?,?,?,?,?,?,?,?,?)',(name,norm,sid,station.get('statNm') if station else None,station.get('addr') if station else None,status,'manual_documented' if (name,sid) in manual_holds else bridge_methods[f['id']] if auto else 'bridge_review',score,evidence or reason,now() if auto else None))
                db.execute('INSERT OR REPLACE INTO match_evidence VALUES (?,?,?)',(name,sid,json.dumps(details,ensure_ascii=False)))
            db.execute('INSERT OR REPLACE INTO analysis_meta VALUES (?,?)',('bridge',json.dumps(metadata,ensure_ascii=False)))
            db.execute('INSERT OR REPLACE INTO analysis_meta VALUES (?,?)',('d1_types',json.dumps({n:sorted(t) for n,t in history.items()},ensure_ascii=False)))
            db.execute('INSERT OR REPLACE INTO analysis_meta VALUES (?,?)',('matching',json.dumps({'generated_at':now(),'method':'D1 -> OA-21712 -> ME','source_sha256':source.get('sha256')})))
        self.prepare_d2();self.export_matches()
        overview=self.overview();counts={'oneHourFacilities':0,'twoHourFacilities':0}
        for station in overview['items']:
            result=self.maintenance(station['statId'])
            counts['oneHourFacilities']+=bool(result['oneHour']);counts['twoHourFacilities']+=bool(result['twoHour'])
        prepared={'prepared_at':now(),'coreFacilities':overview['total'],'analysisReadyFacilities':sum(s['analysis_ready'] for s in overview['items']),'recoveryCandidates':len(overview['priorities']),'potentialCandidates':len(overview['potential']),'stale':overview['stale'],**counts}
        with self.db() as db:db.execute('INSERT OR REPLACE INTO analysis_meta VALUES (?,?)',('research_prepared',json.dumps(prepared)))
        return {**self.quality(),'prepared':prepared}

    def prepare_d2(self):
        path=self.find_source(D2)
        if not path:
            metadata={'available':False,'needed':'data/input/'+D2}
        else:
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            if self.meta('d2').get('sha256')==digest and self.meta('d2').get('parser_version')==2:return self.meta('d2')
            rows=[];header=None;seen=Counter();flags_total=Counter();names=set()
            for rownum,values in xlsx_rows(path):
                if header is None:
                    if all(k in values for k in ('충전소명','충전시작시간','충전종료시간','충전량(kW)')):header=values
                    continue
                if not any(values):continue
                raw=dict(zip(header,values));flags=[];name=raw.get('충전소명','');names.add(name)
                def parse(v):
                    try:return datetime.fromisoformat(str(v)).replace(tzinfo=None)
                    except (ValueError,TypeError):
                        try:return datetime(1899,12,30)+timedelta(days=float(v))
                        except (ValueError,TypeError,OverflowError):return None
                start,end=map(parse,(raw.get('충전시작시간'),raw.get('충전종료시간')))
                if not name or start is None or end is None:flags.append('MISSING_OR_INVALID_DATETIME')
                if start and end and start>end:flags.append('START_AFTER_END')
                energy=number(raw.get('충전량(kW)'))
                if energy is None or energy<0:flags.append('INVALID_ENERGY')
                signature=tuple(values);seen[signature]+=1
                if seen[signature]>1:flags.append('DUPLICATE_SUSPECT')
                flags_total.update(flags)
                # Original rows, including suspected duplicates and bad rows, are retained.
                derived={'weekday':start.weekday(),'hour':start.hour,'month':start.month,'half':1 if start.month<=6 else 2,'timezone':'Asia/Seoul'} if start else {}
                rows.append((rownum,name,normalize_name(name),start.isoformat() if start else None,end.isoformat() if end else None,raw.get('충전량(kW)'),json.dumps(flags),json.dumps({'original':raw,'derived':derived},ensure_ascii=False)))
            if header is None:raise ValueError('D2 필수 컬럼 확인 필요')
            with self.db() as db:
                db.execute('DELETE FROM d2_sessions');db.executemany('INSERT INTO d2_sessions VALUES (?,?,?,?,?,?,?,?)',rows)
            metadata={'available':True,'path':str(path),'sha256':digest,'parser_version':2,'rows':len(rows),'unique_station_names':len(names),'columns':header,'flags':dict(flags_total),'year':2025,'timezone':'Asia/Seoul','coverage_policy':'세션이 관측된 날짜만 분모; 무기록일을 0으로 채우지 않음','original_energy_unit':'충전량(kW)'}
        with self.db() as db:db.execute('INSERT OR REPLACE INTO analysis_meta VALUES (?,?)',('d2',json.dumps(metadata,ensure_ascii=False)))
        return metadata

    def match_rows(self):
        rows=super().match_rows()
        with self.db() as db:details={(n,s):json.loads(b) for n,s,b in db.execute('SELECT * FROM match_evidence')}
        for r in rows:r.update(details.get((r['d1_station_name'],r['candidate_stat_id']),{}))
        return rows

    def export_matches(self):
        rows=self.match_rows();folder=self.path.parent/'analysis';folder.mkdir(exist_ok=True)
        with (folder/'station-match-review.csv').open('w',encoding='utf-8-sig',newline='') as f:
            cols=['d1_station_name','candidate_stat_id','d3_station_name','d3_address','match_status','match_method','match_confidence','review_note','annualFastKwh2025','match_evidence','confidence_reason','evidence','hold_reason','hold_reason_code']
            w=csv.DictWriter(f,fieldnames=cols,extrasaction='ignore');w.writeheader();w.writerows(rows)

    def match_summary(self):
        statuses={}
        for r in self.match_rows():
            n=r['d1_station_name'];status=r['match_status']
            if n not in statuses or status in CONFIRMED or status=='review' and statuses[n]=='unmatched':statuses[n]=status
        c=Counter(statuses.values())
        return {'confirmed':sum(c[k] for k in CONFIRMED),'confirmed_auto':c['confirmed_auto'],'confirmed_manual':c['confirmed_manual']+c['confirmed'],'review':c['review'],'unmatched':c['unmatched']}

    def review(self,name,sid,action,evidence):
        if action not in ('confirm','hold'):raise ValueError('지원하지 않는 검토 동작')
        if len(evidence.strip())<12:raise ValueError('독립 주소/시설 확인 근거 또는 보류 이유를 12자 이상 기록하세요')
        if action=='confirm' and not any(word in evidence.casefold() for word in ('주소','시설대장','공식','충전기','address','registry','coordinates')):raise ValueError('독립 시설 확인 근거를 명시하세요')
        with self.db() as db:
            row=db.execute('SELECT 1 FROM station_match WHERE d1_station_name=? AND candidate_stat_id=?',(name,sid)).fetchone()
            if not row:raise ValueError('후보 없음')
            if action=='confirm':
                if not sid:raise ValueError('D3 후보 필요')
                if db.execute("SELECT 1 FROM station_match WHERE candidate_stat_id=? AND d1_station_name!=? AND match_status IN ('confirmed','confirmed_auto','confirmed_manual')",(sid,name)).fetchone():raise ValueError('이미 다른 D1 시설과 확정된 D3')
                db.execute("UPDATE station_match SET match_status='review' WHERE d1_station_name=?",(name,))
            db.execute('UPDATE station_match SET match_status=?,review_note=?,match_method=?,reviewed_at=? WHERE d1_station_name=? AND candidate_stat_id=?',('confirmed_manual' if action=='confirm' else 'review',evidence,'manual_documented',now(),name,sid))
            old=db.execute('SELECT body FROM match_evidence WHERE d1_name=? AND stat_id=?',(name,sid)).fetchone()
            body=json.loads(old[0]) if old else {};body.update(evidence=evidence if action=='confirm' else '',match_evidence=evidence if action=='confirm' else '',confidence_reason=evidence,hold_reason='' if action=='confirm' else evidence,hold_reason_code='' if action=='confirm' else 'manual_hold')
            db.execute('INSERT OR REPLACE INTO match_evidence VALUES (?,?,?)',(name,sid,json.dumps(body,ensure_ascii=False)))
        self.export_matches()
        return self.match_summary()

    def equipment(self):
        # Speed evidence applies to an identified charger, never all units by name alone.
        with self.db() as db:links=[(sid,json.loads(body)['facility']) for sid,body in db.execute('SELECT stat_id,body FROM bridge_d3')]
        result={};mixed=set()
        for sid,f in links:
            units=defaultdict(list)
            for row in f['rows']:units[charger_key(row['CHARG_ID'])].append(row)
            speeds={bridge_speed(r) for r in f['rows']}
            if speeds!={'FAST'}:mixed.add(sid)
            for cid,rows in units.items():
                kinds={bridge_speed(r) for r in rows}
                distinct={(r['CHARG_TYPE'],r['CHARG_CPCT']) for r in rows}
                if len(kinds)==1 and 'CONFLICT' not in kinds and len(distinct)==1:result[(sid,cid)]={'speed':next(iter(kinds)),'rows':rows,'facility':f}
        return result,mixed

    def stations(self,preview=False,replay=False):
        signature=(preview,replay,self.path.stat().st_mtime_ns,self.external.storage.state('ME').get('last_success_at'),self.external.is_fresh())
        if getattr(self,'_station_key',None)==signature:return copy.deepcopy(self._station_cache)
        links=self.match_rows();by_name=defaultdict(list)
        for r in links:by_name[r['d1_station_name']].append(r)
        selected=[r for r in links if r['match_status'] in CONFIRMED]
        if preview:
            # Require uniqueness among ALL exact-name D3 facilities, not a top-N shortlist.
            names=defaultdict(set)
            for s in self.d3_stations():names[normalize_name(s.get('statNm'))].add(s['statId'])
            normalized_d1=Counter(normalize_name(n) for n in by_name)
            selected += [r for r in links if r['match_status']=='review' and normalized_d1[normalize_name(r['d1_station_name'])]==1 and not any(x['match_status'] in CONFIRMED for x in by_name[r['d1_station_name']]) and normalize_name(r['d1_station_name'])==normalize_name(r.get('d3_station_name')) and len(names[normalize_name(r['d1_station_name'])])==1]
        with self.db() as db:demands={n:(v,json.loads(m)) for n,_,v,m,_ in db.execute('SELECT * FROM d1_demand')}
        equipment,mixed=self.equipment();fresh=self.external.is_fresh() or replay;grouped=defaultdict(list)
        histories=self.meta('d1_types')
        for raw,ts in self.external.storage.rows():grouped[str(raw['statId'])].append(model(raw,self.external.settings,ts,fresh))
        items=[]
        for link in selected:
            sid=link['candidate_stat_id'];cs=[c for c in grouped[sid] if c.get('delYn')=='N' and c.get('latitude') is not None and c.get('longitude') is not None]
            if histories.get(normalize_name(link['d1_station_name']),[])!=['급속']:mixed.add(sid)
            if not cs:continue
            fast=[];unknown=[]
            for c in cs:
                proof=equipment.get((sid,charger_key(c['chgerId'])))
                if proof and proof['speed']=='FAST':
                    if str(c.get('chgerType')) in ('02','08'):unknown.append(c);continue
                    capacities=[number(re.search(r'(\d+(?:\.\d+)?)\s*kW',str(r.get('CHARG_CPCT','')),re.I).group(1)) for r in proof['rows'] if re.search(r'(\d+(?:\.\d+)?)\s*kW',str(r.get('CHARG_CPCT','')),re.I)]
                    if capacities and c['output_kw'] not in capacities:unknown.append(c);continue
                    fast.append(dict(c,analysis_eligible=True,charging_speed='FAST',classification_verified=True))
                elif not proof or proof['speed'] not in ('SLOW',):unknown.append(c)
            first=cs[0];annual,monthly=demands[link['d1_station_name']]
            ready=bool(fast) and not unknown and all(c['output_kw'] is not None and c['output_kw']>0 for c in fast)
            def power(units):return sum(c['output_kw'] for c in units) if ready else None
            items.append({'analysisStationId':'ME:'+sid,'statId':sid,'statNm':first.get('statNm'),'addr':first.get('addr'),'lat':first['latitude'],'lng':first['longitude'],'d1StationName':link['d1_station_name'],'annualFastKwh2025':annual,'monthlyFastKwh2025':monthly,'chargerCount':len(fast) if ready else None,'rawChargerCount':len(cs),'chargers':fast if ready else cs,'totalRatedOutputKw':power(fast),'availableRatedOutputKw':power([c for c in fast if c['status'] in ('AVAILABLE','CHARGING')]) if fresh else None,'stoppedRatedOutputKw':power([c for c in fast if c['status']=='STOPPED']) if fresh else None,'matchStatus':'confirmed' if link['match_status'] in CONFIRMED else 'review','confirmationKind':link['match_status'],'analysis_ready':ready,'classificationVerified':ready,'maintenance_analysis_status':'READY' if ready and sid not in mixed else 'HOLD_MIXED' if sid in mixed else 'HOLD_CLASSIFICATION','unknownEquipmentCount':len(unknown),'statusCounts':{k:sum(c['status']==k for c in fast) if ready and fresh else None for k in ('AVAILABLE','CHARGING','STOPPED','MAINTENANCE','UNKNOWN','COMM_ERROR')},'useTime':first.get('useTime'),'evidence':link.get('evidence') or link['review_note']})
        source=self.meta('d1')
        result={'items':items,'total':len(items),'matching':self.match_summary(),'d1':source,'d1Available':source.get('available',False),'stationMatchingReady':bool(links),'analysisDatasetReady':any(s['analysis_ready'] for s in items),'classificationVerified':bool(items) and all(s['analysis_ready'] for s in items),'rawChargerCount':self.external.storage.charger_count(),'last_success_at':self.external.storage.state('ME').get('last_success_at'),'preview':preview,'replay':replay,'stale':not self.external.is_fresh()}
        self._station_key=signature;self._station_cache=copy.deepcopy(result)
        return result

    def quality(self):
        summary=self.match_summary()
        with self.db() as db:
            total=db.execute('SELECT SUM(annual_fast_kwh),COUNT(*) FROM d1_demand').fetchone()
            linked=db.execute("SELECT SUM(annual_fast_kwh) FROM d1_demand WHERE d1_station_name IN (SELECT d1_station_name FROM station_match WHERE match_status IN ('confirmed','confirmed_auto','confirmed_manual'))").fetchone()[0] or 0
            d2_names={r[0] for r in db.execute('SELECT DISTINCT normalized_name FROM d2_sessions')}
            d2_counts=dict(db.execute('SELECT normalized_name,COUNT(*) FROM d2_sessions GROUP BY normalized_name'))
        core=self.stations()['items']
        linked_rows=sum(d2_counts.get(normalize_name(s['d1StationName']),0) for s in core)
        return {'d1':self.meta('d1'),'bridge':self.meta('bridge'),'d2':self.meta('d2'),'matching':summary,'facilityConnectionRate':summary['confirmed']/total[1] if total[1] else None,'kwhConnectionRate':linked/total[0] if total[0] else None,'confirmedFastKwh':linked,'totalFastKwh':total[0],'d2LinkedFacilities':sum(normalize_name(s['d1StationName']) in d2_names for s in core),'d2LinkedRows':linked_rows,'d2LinkedRowRate':linked_rows/sum(d2_counts.values()) if d2_counts else None,'maintenanceReadyFacilities':sum(s['maintenance_analysis_status']=='READY' and normalize_name(s['d1StationName']) in d2_names for s in core),'analysisHolds':[{'statId':s['statId'],'name':s['statNm'],'unknownEquipmentCount':s['unknownEquipmentCount'],'maintenanceStatus':s['maintenance_analysis_status']} for s in core if not s['analysis_ready'] or s['maintenance_analysis_status']!='READY'],'prepared':self.meta('research_prepared')}

    def funnel(self):
        # Counts can describe the last real observation, without declaring it current.
        stale=not self.external.is_fresh();data=self.overview(replay=stale)
        stations=data['items'];units=[c for s in stations for c in s['chargers']]
        potential=data['potential'];summary=self.match_summary();reasons={}
        for r in self.match_rows():
            if r['match_status']=='review':reasons.setdefault(r['d1_station_name'],r.get('hold_reason_code') or 'manual_review_required')
        return {'d1FastFacilities':self.meta('d1').get('fast_station_names'),
                'confirmed':summary['confirmed'],'review':summary['review'],
                'equipmentReadyFacilities':sum(s['analysis_ready'] for s in stations),
                'potentialImpactChargers':len(potential),
                'exactImpactChargers':sum(not r['scoreIsUpperBound'] for r in potential),
                'upperBoundImpactChargers':sum(r['scoreIsUpperBound'] for r in potential),
                'observedCoreStopped':sum(c.get('stat')=='4' for s in stations if s['analysis_ready'] for c in s['chargers']),
                'currentCoreStopped':None if stale else sum(c.get('stat')=='4' for s in stations if s['analysis_ready'] for c in s['chargers']),
                'observedRecoveryCandidates':len(data['priorities']),
                'currentRecoveryCandidates':None if stale else len(data['priorities']),
                'observationAt':data['last_success_at'],'stale':stale,
                'reviewReasons':dict(Counter(reasons.values())),
                'exclusionReasons':{
                    'unconfirmed_match':{'count':summary['review']+summary['unmatched'],'unit':'facility'},
                    'missing_output':{'count':sum(c['output_kw'] is None or c['output_kw']<=0 for c in units),'unit':'charger'},
                    'fast_type_unverified':{'count':sum(s['unknownEquipmentCount'] for s in stations),'unit':'charger'},
                    'stale_status':{'count':len(units) if stale else 0,'unit':'charger'},
                    'restricted_access':{'count':sum(c.get('limitYn')!='N' for c in units),'unit':'charger_attribute'},
                    'alternative_network_uncertain':{'count':sum(r['scoreIsUpperBound'] for r in potential),'unit':'impact_charger'},
                    'not_stopped':{'count':sum(r['raw_stat']!='4' for r in potential),'unit':'impact_charger'}}}

    def overview(self,radius=500,weight='equal',preview=False,replay=False):
        if radius not in (500,1000) or weight not in WEIGHTS:raise ValueError('반경/가중치 선택 오류')
        signature=(radius,weight,preview,replay,self.path.stat().st_mtime_ns,self.external.storage.state('ME').get('last_success_at'),self.external.is_fresh())
        if signature in getattr(self,'_overview_cache',{}):return self._overview_cache[signature]
        data=self.stations(preview,replay);stations=data['items'];ready=[s for s in stations if s['analysis_ready'] and s['annualFastKwh2025'] is not None and s['annualFastKwh2025']>=0]
        ranks=average_ranks({s['statId']:s['annualFastKwh2025'] for s in ready});equipment,_=self.equipment();types,states=classifications(self.external.settings)
        network=[]
        for raw,ts in self.external.storage.rows():
            if raw.get('delYn')!='N':continue
            # v1.25 explicitly calls 02/08 slow; they cannot supply rapid alternatives.
            if str(raw.get('chgerType')) in ('02','08'):continue
            r=model(raw,self.external.settings,ts,not data['stale'] or replay)
            if r['latitude'] is None:continue
            proof=equipment.get((str(r['statId']),charger_key(r['chgerId'])))
            if proof and proof['speed']=='SLOW':continue
            compatible=bool(proof and proof['speed']=='FAST' and str(r.get('chgerType')) not in ('02','08'))
            if compatible:
                capacities=[number(m.group(1)) for row in proof['rows'] if (m:=re.search(r'(\d+(?:\.\d+)?)\s*kW',str(row.get('CHARG_CPCT','')),re.I))]
                if capacities and r['output_kw'] not in capacities:compatible=False
            fast=compatible or str(r.get('chgerType')) in types
            network.append(dict(r,fast_confirmed=fast,lat=r['latitude'],lng=r['longitude']))
        potential=[];held=[]
        for s in stations:
            s['alternativeOutput']={};s['excludedAlternativeCount']={};s['restrictedAlternativeCount']={}
            for rad in (500,1000):
                nearby=[c for c in network if str(c['statId'])!=s['statId'] and abs(c['lat']-s['lat'])<.011 and abs(c['lng']-s['lng'])<.014 and distance(s,c)<=rad]
                normal=[c for c in nearby if c['fast_confirmed'] and c['status'] in ('AVAILABLE','CHARGING') and c.get('limitYn')=='N']
                s['alternativeOutput'][str(rad)]=sum(c['output_kw'] for c in normal) if (not data['stale'] or replay) and all(c['output_kw'] is not None and c['output_kw']>0 for c in normal) else None
                s['excludedAlternativeCount'][str(rad)]=sum(not c['fast_confirmed'] and c.get('chgerType') not in ('02','08') for c in nearby)
                s['restrictedAlternativeCount'][str(rad)]=sum(c.get('limitYn')!='N' for c in nearby)
            P=s['totalRatedOutputKw'];A=s['alternativeOutput'][str(radius)];D=ranks.get(s['statId'])
            for c in s['chargers']:
                why=[]
                if not s['analysis_ready']:why.append('공식 설비 유형/ID/출력 교차확인 필요')
                if data['stale'] and not replay:why.append('최신 상태 관측 필요')
                if D is None:why.append('D1 유효 충전량 필요')
                if A is None:why.append('대체망 출력 확인 필요')
                Q=c['output_kw']/P if P and c['output_kw'] is not None else None;B=P/(P+A) if P and A is not None else None
                score=sum(v*w for v,w in zip((D,Q,B),WEIGHTS[weight])) if not why and all(v is not None for v in (D,Q,B)) else None
                item={'charger_id':s['analysisStationId']+':'+str(c['chgerId']),'station_id':s['analysisStationId'],'statId':s['statId'],'chgerId':str(c['chgerId']),'name':s['statNm'],'power_kw':c['output_kw'],'status':c['status'],'raw_stat':c.get('stat'),'statUpdDt':c.get('statUpdDt'),'D':D,'Q':Q,'B':B,'score':score,'eligible':score is not None,'reasons':why,'alternative_kw':A,'alternative500':s['alternativeOutput']['500'],'alternative1000':s['alternativeOutput']['1000'],'alternative_unknown_count':s['excludedAlternativeCount'][str(radius)]}
                item['scoreIsUpperBound']=item['alternative_unknown_count']>0
                if score is not None:potential.append(item)
                else:held.append(item)
        potential.sort(key=lambda r:(-r['score'],-r['power_kw'],r['statId'],r['chgerId']))
        for i,r in enumerate(potential,1):r['rank']=i
        recovery=[dict(r) for r in potential if r['raw_stat']=='4' and r['status']=='STOPPED' and not r['scoreIsUpperBound']]
        held.extend(dict(r,eligible=False,reasons=['주변 급속 유형 미확인: B/Impact는 상한이며 최종 복구순위 보류']) for r in potential if r['raw_stat']=='4' and r['scoreIsUpperBound'])
        for i,r in enumerate(recovery,1):r['rank']=i
        high={r['charger_id'] for r in potential[:math.ceil(len(potential)*.2)]}
        cumulative=[];value=0
        for r in recovery:value+=r['power_kw'];cumulative.append({'rank':r['rank'],'cumulativeKw':value})
        result={**data,'priorities':recovery,'potential':potential,'held':held,'highImpactIds':sorted(high),'radius':radius,'weight':weight,'weights':WEIGHTS[weight],'cumulative':cumulative,'algorithm':'D average percentile rank; Q=charger/P; B=P/(P+A)','alternativeScope':'공식 시설대장 또는 검증된 ME 코드로 확인된 급속 대체망; 유형 미확인 설비는 제외 건수 별도 표시. 미확인 설비가 있으면 B는 실제 부족도의 상한이며 연구 최종 해석에 주의.','previewWarning':'검토용 미확정 분석 · 최종 연구결과가 아님' if preview else None}
        if len(getattr(self,'_overview_cache',{}))>8:self._overview_cache={}
        if not hasattr(self,'_overview_cache'):self._overview_cache={}
        self._overview_cache[signature]=result
        return result

    def simulate(self,ids,radius=500,weight='equal',preview=False,hypothetical=False,replay=False):
        data=self.overview(radius,weight,preview,replay);ids=set(ids)
        lookup={r['charger_id']:r for r in (data['potential'] if hypothetical else data['priorities'])}
        if not ids<=lookup.keys():raise ValueError('현재 유효한 분석대상 설비만 선택할 수 있습니다')
        selected=[lookup[i] for i in ids]
        if hypothetical and any(r['status'] not in ('AVAILABLE','CHARGING') for r in selected):raise ValueError('가정 고장은 현재 정상 설비만 선택할 수 있습니다')
        cs=[c for s in data['items'] if s['analysis_ready'] for c in s['chargers']]
        valid=not data['stale'] or replay;power=lambda status:sum(c['output_kw'] for c in cs if c['status'] in status) if valid else None
        before={'normalKw':power(('AVAILABLE','CHARGING')),'stoppedKw':power(('STOPPED',)),'maintenanceKw':power(('MAINTENANCE',)),'stoppedCount':sum(c['status']=='STOPPED' for c in cs) if valid else None,'highImpactUnrestored':sum(r['charger_id'] in data['highImpactIds'] for r in data['priorities']) if valid else None}
        delta=sum(r['power_kw'] for r in selected)
        if hypothetical and valid:
            before['normalKw']-=delta;before['stoppedKw']+=delta;before['stoppedCount']+=len(selected)
            before['highImpactUnrestored']+=sum(i in data['highImpactIds'] for i in ids)
        after=copy.deepcopy(before)
        if valid:after.update(normalKw=before['normalKw']+delta,stoppedKw=before['stoppedKw']-delta,stoppedCount=before['stoppedCount']-len(selected),highImpactUnrestored=max(0,before['highImpactUnrestored']-sum(i in data['highImpactIds'] for i in ids)))
        return {'before':before,'after':after,'recoveredKw':delta if valid else None,'recoveryRate':delta/before['normalKw']*100 if valid and before['normalKw']>0 else None,'selectedIds':sorted(ids),'hypothetical':hypothetical,'preview':preview,'replay':replay,'warning':('과거 관측 재현 · 현재 결과가 아님 · ' if replay else '')+('가정 시나리오 · 실제 운영중지 결과가 아님' if hypothetical else '가상 복구 시나리오 · 실제 복구 결과가 아님'),'observationAt':data['last_success_at'],'stale':data['stale']}

    def maintenance(self,sid,preview=False):
        station=next((s for s in self.stations(preview)['items'] if s['statId']==sid),None)
        if not station:raise ValueError('핵심 분석시설 없음')
        if not self.meta('d2').get('available'):return {'status':'MISSING_D2','message':'정비시간 분석을 위해 OA-22258 자료가 필요합니다.','heatmap':None,'oneHour':[],'twoHour':[]}
        if station['maintenance_analysis_status']!='READY':return {'status':station['maintenance_analysis_status'],'message':'정비시간 분석 보류 · 혼합시설 또는 급속 전용 근거 부족','heatmap':None,'oneHour':[],'twoHour':[]}
        with self.db() as db:rows=db.execute('SELECT start_at,end_at,flags FROM d2_sessions WHERE normalized_name=?',(normalize_name(station['d1StationName']),)).fetchall()
        sessions=[]
        for start,end,flags in rows:
            bad=set(json.loads(flags))-{'DUPLICATE_SUSPECT'}
            if not bad and start and end and start[:4]=='2025':sessions.append((datetime.fromisoformat(start),datetime.fromisoformat(end)))
        days=defaultdict(list)
        for a,b in sessions:days[a.date()].append((a,b))
        starts=sorted(a for a,b in sessions);ends=sorted(b for a,b in sessions)
        heat=[]
        for weekday in range(7):
            observed=[d for d in days if d.weekday()==weekday]
            heat.append([sum(a.hour==hour for d in observed for a,b in days[d])/len(observed) if observed else None for hour in range(24)])
        use_time=str(station.get('useTime') or '')
        all_day='24' in use_time and ('시간' in use_time or '시' in use_time)
        if not all_day:
            match=re.search(r'(\d{1,2}):(\d{2})\s*[~～\-]\s*(\d{1,2}):(\d{2})',use_time)
            if match:
                a,b,c,d=map(int,match.groups());allowed=(a*60+b,c*60+d)
            else:return {'status':'HOLD_OPERATING_HOURS','message':'운영시간 확인 후 후보 생성 가능','heatmap':heat,'oneHour':[],'twoHour':[]}
        else:allowed=(0,1440)
        # Active-at-start is a record count, not a charger count. Use all spanning sessions.
        results={}
        for duration in (60,120):
            candidates=[]
            for weekday in range(7):
                observed=sorted(d for d in days if d.weekday()==weekday)
                if not observed:continue
                for hour in range(24):
                    minute=hour*60
                    if not all_day:
                        if allowed[0]<=allowed[1] and (minute<allowed[0] or minute+duration>allowed[1]):continue
                        if allowed[0]>allowed[1] and not (minute>=allowed[0] and minute+duration<=allowed[1]+1440 or minute+duration<=allowed[1]):continue
                    costs=[];active=[];halves=defaultdict(list)
                    for day in observed:
                        start=datetime.combine(day,datetime.min.time())+timedelta(minutes=minute);end=start+timedelta(minutes=duration)
                        if minute+duration>1440 and day+timedelta(days=1) not in days:continue
                        source=days[day]+days.get(day+timedelta(days=1),[]) if minute+duration>1440 else days[day]
                        n=sum(start<=a<end for a,b in source);costs.append(n)
                        active.append(bisect_right(starts,start)-bisect_right(ends,start))
                        halves[1 if day.month<=6 else 2].append(n)
                    if not costs:continue
                    stability=abs(sum(halves[1])/len(halves[1])-sum(halves[2])/len(halves[2])) if halves[1] and halves[2] else None
                    candidates.append({'weekday':weekday,'startMinute':minute,'duration':duration,'avgStarts':sum(costs)/len(costs),'validDays':len(costs),'avg_active_at_window_start':sum(active)/len(active),'seasonalStability':stability,'confidence':'관측일 기준 · 제한적' if len(costs)<20 or stability is None else '관측일 기준 · 양 반기 비교 가능'})
            candidates.sort(key=lambda c:(c['avgStarts'],c['avg_active_at_window_start'],c['seasonalStability'] if c['seasonalStability'] is not None else math.inf,-c['validDays'],c['weekday'],c['startMinute']))
            results['oneHour' if duration==60 else 'twoHour']=candidates[:3]
        return {'status':'READY' if sessions else 'NO_LINKED_SESSIONS','message':'계획정비 후보시간 · 긴급복구를 미루는 권고가 아님','heatmap':heat,'unit':'관측일 평균 충전 시작건수','validDaysByWeekday':[sum(d.weekday()==w for d in days) for w in range(7)],'sessionCount':len(sessions),'coverageNote':'세션 관측일만 분모로 사용. 무기록일은 결측이며 전체 운영일 커버리지를 보장하지 않음. 중복 의심행은 원본과 함께 보존.','year':2025,**results}
