import copy, math
from datetime import datetime,timedelta,timezone
KST=timezone(timedelta(hours=9))
FORMULA_VERSION='impact-mean-v0.2'
NORMAL={'AVAILABLE','CHARGING','RESTORED'}
def distance(a,b):
    x,y,u,v=map(math.radians,(a['lat'],a['lon'],b['lat'],b['lon']))
    z=math.sin((u-x)/2)**2+math.cos(x)*math.cos(u)*math.sin((v-y)/2)**2
    return 6371008.8*2*math.asin(min(1,math.sqrt(z)))
def fresh(c,at):
    try:
        age=(datetime.fromisoformat(at)-datetime.fromisoformat(c['last_verified_at'])).total_seconds()
        return 0<=age<=c.get('ttl_minutes',15)*60
    except (ValueError,TypeError,KeyError): return False
def state(c,at):
    if c.get('deleted'): return 'DELETED'
    return c.get('status','UNKNOWN') if fresh(c,at) else 'UNKNOWN'
def eligibility(s):
    issues=list(s.get('quality_flags',[]))
    if s.get('match_status')!='approved': issues.append('시설 매칭 미승인')
    if s.get('annual_kwh') is None or s.get('annual_kwh',-1)<0: issues.append('급속 실적 결측')
    if not all(isinstance(s.get(k),(int,float)) and math.isfinite(s[k]) for k in ('lat','lon')) or not (-90<=s.get('lat',999)<=90 and -180<=s.get('lon',999)<=180): issues.append('좌표 미확인')
    cs=[c for c in s['chargers'] if not c.get('deleted')]
    if not cs or any(not isinstance(c.get('power_kw'),(int,float)) or c['power_kw']<=0 or not math.isfinite(c['power_kw']) for c in cs): issues.append('정격출력 불완전')
    if any(not c.get('physical_verified') or not c.get('sharing_verified') for c in cs): issues.append('물리 설비·공유출력 미확인')
    if any(not c.get('fast_verified') for c in cs): issues.append('급속 유형 미확인')
    return list(dict.fromkeys(issues))
def totals(stations,at):
    out=dict(total_kw=0.,normal_kw=0.,stopped_kw=0.,uncertain_kw=0.,available_kw=0.,charger_count=0,missing_power_count=0,normal_count=0,stopped_count=0,maintenance_count=0,uncertain_count=0)
    for s in stations:
        seen=set()
        for c in s['chargers']:
            if c.get('deleted'): continue
            physical=c.get('physical_unit_id') or c['id']
            if physical in seen: continue
            seen.add(physical); out['charger_count']+=1
            status=state(c,at)
            out['normal_count' if status in NORMAL else 'stopped_count' if status=='STOPPED' else 'maintenance_count' if status=='MAINTENANCE' else 'uncertain_count']+=1
            p=c.get('power_kw')
            if not isinstance(p,(int,float)) or p<=0 or not math.isfinite(p): out['missing_power_count']+=1; continue
            out['total_kw']+=p
            status=state(c,at)
            out['normal_kw' if status in NORMAL else 'stopped_kw' if status=='STOPPED' else 'uncertain_kw']+=p
            if status=='AVAILABLE': out['available_kw']+=p
    return out
def alternatives(station,stations,radius,at):
    rows=[]
    for s in stations:
        if s['id']==station['id'] or not all(isinstance(s.get(k),(int,float)) for k in ('lat','lon')): continue
        d=distance(station,s)
        if d>radius+1e-7: continue
        for c in s['chargers']:
            trusted_network=c.get('provider_alternative_eligible') is True and c.get('fast_verified') is True
            if state(c,at) in NORMAL and (trusted_network or all(c.get(k) for k in ('fast_verified','physical_verified','sharing_verified','access_verified','compatible_verified'))) and isinstance(c.get('power_kw'),(int,float)) and c['power_kw']>0:
                rows.append(dict(station_id=s['id'],charger_id=c['id'],distance_m=round(d,2),power_kw=c['power_kw'],physical_unit_id=c.get('physical_unit_id',c['id'])))
    return list({(r['station_id'],r['physical_unit_id']):r for r in rows}.values())
def percentile(values,p=.95):
    if not values: return None
    a=sorted(values); x=(len(a)-1)*p; i=int(x)
    return a[i]+(a[min(i+1,len(a)-1)]-a[i])*(x-i)
def legacy_impact(d,p,total,alt,k=200): return 100*d*(p/total)*(k/(k+alt))
def impact(d,p,total,alt,k=200): return (d+p/total+k/(k+alt))/3
def analyze(snapshot,radius=500,at=None,q95=None):
    at=at or snapshot['observed_at']; stations=copy.deepcopy(snapshot['stations'])
    targets=[s for s in stations if s.get('analysis_target',True)]
    if q95 is None: q95=percentile([s['annual_kwh'] for s in targets if not eligibility(s)])
    ranks,held=[],[]
    for s in targets:
        s['totals']=totals([s],at); reasons=eligibility(s); s['quality_flags']=reasons
        alt=alternatives(s,stations,radius,at) if not any('좌표' in x for x in reasons) else []
        s['alternative_kw']=sum(r['power_kw'] for r in alt)
        s['demand_factor']=min(1.,math.log1p(s['annual_kwh'])/math.log1p(q95)) if not reasons and q95 and q95>0 else None
        seen=set()
        for c in s['chargers']:
            c['display_status']=state(c,at); physical=c.get('physical_unit_id',c['id'])
            if physical in seen: continue
            seen.add(physical)
            if c.get('status')!='STOPPED': continue
            why=reasons.copy()
            if not fresh(c,at): why.append('상태 최신성 미충족')
            if not snapshot.get('network_complete'): why.append('주변 대체망 수집 범위 미확인')
            if not q95 or q95<=0: why.append('수요 정규화 기준 없음')
            row=dict(charger_id=c['id'],station_id=s['id'],name=s['name'],district=s.get('district','미확인'),power_kw=c.get('power_kw'),score=None,reasons=why,eligible=not why,demand_factor=s['demand_factor'],share_factor=None,shortage_factor=None,alternative_kw=s['alternative_kw'],status=state(c,at))
            if not why:
                row['share_factor']=c['power_kw']/s['totals']['total_kw']; row['shortage_factor']=200/(200+s['alternative_kw'])
                row['score']=impact(row['demand_factor'],c['power_kw'],s['totals']['total_kw'],s['alternative_kw'])
                row.update(D=row['demand_factor'],Q=row['share_factor'],B=row['shortage_factor'])
            (held if why else ranks).append(row)
    ranks.sort(key=lambda r:(-r['score'],r['charger_id']))
    for i,r in enumerate(ranks,1): r['rank']=i
    map_stations=[]
    target_ids={s['id'] for s in targets}
    for station in stations:
        if not all(isinstance(station.get(k),(int,float)) and math.isfinite(station[k]) for k in ('lat','lon')) or not (-90<=station['lat']<=90 and -180<=station['lon']<=180): continue
        near=[target['id'] for target in targets if target['id']!=station['id'] and all(isinstance(target.get(k),(int,float)) for k in ('lat','lon')) and distance(target,station)<=radius+1e-7]
        if snapshot.get('provider_inventory') or station['id'] in target_ids or near:
            station['near_target_ids']=near
            station.setdefault('totals',totals([station],at))
            for charger in station['chargers']: charger['display_status']=state(charger,at)
            map_stations.append(station)
    return dict(stations=targets,map_stations=map_stations,priorities=ranks,held=held,totals=totals(targets,at),q95=q95,radius_m=radius)
def simulate(snapshot,run,ids):
    selected=set(ids); base=analyze(snapshot,run['radius_m'],run['evaluated_at'],run['q95'])
    if not selected<={r['charger_id'] for r in base['priorities']}: raise ValueError('최신 운영중지·승인 설비만 복구할 수 있습니다.')
    newer=copy.deepcopy(snapshot)
    for s in newer['stations']:
        for c in s['chargers']:
            if c['id'] in selected: c['status']='RESTORED'
    after=analyze(newer,run['radius_m'],run['evaluated_at'],run['q95'])
    delta=after['totals']['normal_kw']-base['totals']['normal_kw']
    assert abs(delta-(base['totals']['stopped_kw']-after['totals']['stopped_kw']))<1e-8
    assert base['totals']['total_kw']==after['totals']['total_kw'] and base['totals']['uncertain_kw']==after['totals']['uncertain_kw']
    return dict(before=base,after=after,charger_ids=sorted(selected),recovered_kw=delta,recovery_rate=delta/base['totals']['stopped_kw'] if base['totals']['stopped_kw'] else 0.,stopped_kw_reduction=base['totals']['stopped_kw']-after['totals']['stopped_kw'],baseline_top_count=min(10,len(base['priorities'])),baseline_top_remaining=sum(r['charger_id'] not in selected for r in base['priorities'][:10]))
def overlap_minutes(start,end,a,b): return max(0.,(min(end,b)-max(start,a)).total_seconds()/60)
def maintenance(sessions,covered_days,fast_only_verified,weekday,duration,period_start,period_end,allowed_start=0,allowed_end=1560):
    reasons=[]
    if not fast_only_verified: reasons.append('분석기간 급속 전용 이력 미확인')
    if covered_days is None: reasons.append('관측 커버리지 근거 없음')
    coverage=set(covered_days or [])
    days=[datetime.fromisoformat(d).replace(tzinfo=KST) for d in sorted(coverage) if datetime.fromisoformat(d).weekday()==weekday and period_start.date().isoformat()<=d<period_end.date().isoformat()]
    if len(days)<20: reasons.append('요일별 유효 표본 20일 미만')
    if reasons: return dict(candidates=[],reasons=reasons,valid_days=len(days))
    rows=[]
    for minute in range(0,1440,15):
        if minute<allowed_start or minute+duration>allowed_end: continue
        costs=[]
        for day in days:
            a=day+timedelta(minutes=minute); b=a+timedelta(minutes=duration)
            if b>period_end or (b>day+timedelta(days=1) and (day+timedelta(days=1)).date().isoformat() not in coverage): continue
            costs.append(sum(overlap_minutes(max(x,period_start),min(y,period_end),a,b) for x,y in sessions if y>x))
        if len(costs)>=20: rows.append(dict(start_minute=minute,duration_minutes=duration,mean_session_minutes=sum(costs)/len(costs),valid_days=len(costs),min_session_minutes=min(costs),max_session_minutes=max(costs)))
    chosen=[]
    for row in sorted(rows,key=lambda r:(r['mean_session_minutes'],-r['valid_days'],r['start_minute'])):
        a=row['start_minute']; b=a+duration
        if all(not any(max(a,c['start_minute']+shift)<min(b,c['start_minute']+shift+duration) for shift in (-1440,0,1440)) for c in chosen): chosen.append(row)
        if len(chosen)==3: break
    return dict(candidates=chosen,reasons=[] if chosen else ['작업시간·관측일 조건을 충족하는 후보 없음'],valid_days=len(days))


def session_hourly(sessions,period_start,period_end):
    if not sessions: return None
    values=[[0.]*24 for _ in range(7)]
    for a,b in sessions:
        x=max(a,period_start); stop=min(b,period_end)
        if b<=a: continue
        while x<stop:
            y=min(stop,x.replace(minute=0,second=0,microsecond=0)+timedelta(hours=1))
            values[x.weekday()][x.hour]+=(y-x).total_seconds()/60
            x=y
    return dict(values=values,unit='세션·분',coverage_verified=False,period=['2025-01-01','2025-12-31'],session_count=len(sessions))
