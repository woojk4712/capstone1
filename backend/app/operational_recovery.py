"""Seoul stopped-unit recovery view. Never writes ME/analysis records or collects APIs."""
from collections import Counter,defaultdict
from .research import average_ranks, distance


class OperationalRecovery:
    def __init__(self,view,analysis):
        self.view,self.analysis=view,analysis
        self._cache={}

    def ranking(self,radius=500,observation_at=None,replay=False):
        if radius not in (500,1000):raise ValueError('invalid_radius')
        data=self.view.inventory(observation_at)
        signature=(data['observationAt'],radius,str(self.analysis.path.stat().st_mtime_ns),data['stale'],data['superseded'],replay)
        if signature in self._cache:return self._cache[signature]
        groups=defaultdict(list);network=[];deleted=0;seoul_stopped=0
        for c in data['items']:
            seoul=str(c.get('addr','')).strip().startswith('서울특별시')
            stopped=str(c.get('stat'))=='4'
            if seoul and stopped:seoul_stopped+=1
            if c.get('delYn')=='Y':
                if seoul and stopped:deleted+=1
                continue
            if seoul:groups[str(c['statId'])].append(c)
            if (c['status'] in ('AVAILABLE','CHARGING') and c['latitude'] is not None
                    and c['longitude'] is not None):network.append(c)
        core=self.analysis.stations(replay=True)
        core_lookup={s['statId']:s for s in core['items']}
        demand=average_ranks({s['statId']:s['annualFastKwh2025'] for s in core['items']
                              if s['analysis_ready'] and s['annualFastKwh2025'] is not None and s['annualFastKwh2025']>=0})
        rows=[];stations=[];excluded=Counter();observed_kw=0;missing_stopped_output=0
        for sid,cs in groups.items():
            stopped=[c for c in cs if str(c.get('stat'))=='4']
            if not stopped:continue
            positioned=next((c for c in cs if c['latitude'] is not None and c['longitude'] is not None),None)
            first=positioned or cs[0]
            P=sum(c['output_kw'] for c in cs if c['output_kw'] is not None and c['output_kw']>0)
            A=None;network_missing=0;restricted=0
            if positioned:
                origin={'lat':first['latitude'],'lng':first['longitude']};A=0
                for c in network:
                    if str(c['statId'])==sid:continue
                    if abs(c['latitude']-origin['lat'])>.011 or abs(c['longitude']-origin['lng'])>.014:continue
                    if distance(origin,{'lat':c['latitude'],'lng':c['longitude']})>radius:continue
                    if c.get('limitYn')!='N':restricted+=1;continue
                    if c['output_kw'] is None or c['output_kw']<=0:network_missing+=1;continue
                    A+=c['output_kw']
            stations.append({'analysisStationId':'ME:'+sid,'statId':sid,'statNm':first.get('statNm'),
                             'addr':first.get('addr'),'lat':first['latitude'],'lng':first['longitude'],
                             'chargers':cs,'stoppedChargerCount':len(stopped),'confirmed':sid in core_lookup})
            for c in stopped:
                reasons=[]
                if c['output_kw'] is None or c['output_kw']<=0:reasons.append('missing_output');missing_stopped_output+=1
                else:observed_kw+=c['output_kw']
                if c['latitude'] is None or c['longitude'] is None:reasons.append('missing_coordinates')
                if not data['statusClassificationVerified']:reasons.append('status_unverified')
                for reason in reasons:excluded[reason]+=1
                selectable=not reasons
                Q=c['output_kw']/P if c['output_kw'] is not None and c['output_kw']>0 and P>0 else None
                B=P/(P+A) if P>0 and A is not None else None
                score=(Q+B)/2 if selectable and Q is not None and B is not None and (not data['stale'] or replay) else None
                D=demand.get(sid) if core['last_success_at']==data['observationAt'] else None
                rows.append({'charger_id':'ME:'+sid+':'+str(c['chgerId']),'statId':sid,'chgerId':str(c['chgerId']),
                             'name':first.get('statNm'),'addr':first.get('addr'),'power_kw':c['output_kw'],
                             'status':'STOPPED' if data['statusClassificationVerified'] else 'UNKNOWN','raw_stat':c.get('stat'),
                             'statUpdDt':c.get('statUpdDt'),'Q':Q,'B':B,'P':P,'A':A,
                             'operationalImpact':score,'d1Connected':sid in core_lookup,'D':D,
                             'demandImpact':(D+Q+B)/3 if score is not None and D is not None else None,
                             'annualFastKwh2025':core_lookup.get(sid,{}).get('annualFastKwh2025'),
                             'selectable':selectable,'exclusionReasons':reasons,'networkMissingOutput':network_missing,
                             'networkRestricted':restricted,'facilityMissingOutput':sum(x['output_kw'] is None or x['output_kw']<=0 for x in cs)})
        rows.sort(key=lambda r:(r['operationalImpact'] is None,-(r['operationalImpact'] or 0),-(r['power_kw'] or 0),r['statId'],r['chgerId']))
        for i,r in enumerate(rows,1):r['rank']=i
        value=0;curve=[]
        for r in rows:
            if r['selectable']:value+=r['power_kw'];curve.append({'rank':len(curve)+1,'cumulativeKw':value})
        result={'status':'stale' if data['stale'] and not replay else 'ok','items':rows,'stations':stations,
                'count':len(rows),'stationCount':len(stations),'selectableCount':sum(r['selectable'] for r in rows),
                'observationAt':data['observationAt'],'last_success_at':data['observationAt'],'revision':data['revision'],
                'analysisRevision':str(self.analysis.path.stat().st_mtime_ns),'stale':data['stale'],'replay':replay,
                'superseded':data['superseded'],'radius':radius,'cumulative':curve,
                'reason':None if rows else 'no_current_stopped_seoul_chargers',
                'diagnostics':{'rawSeoulStopped':seoul_stopped,'deletedExcluded':deleted,'operationalStopped':len(rows),
                               'operationalVisibleStopped':sum(r['exclusionReasons'].count('missing_coordinates')==0 for r in rows),
                               'stoppedOutputKw':None if missing_stopped_output else observed_kw,'knownStoppedOutputKw':observed_kw,
                               'excludedSelectableCount':sum(not r['selectable'] for r in rows),'exclusionReasons':dict(excluded),
                               'd1ConnectedStopped':sum(r['d1Connected'] for r in rows),
                               'operationalScoreCount':sum(r['operationalImpact'] is not None for r in rows),
                               'demandScoreCount':sum(r['demandImpact'] is not None for r in rows)},
                'scoreDefinition':'OperationalImpact=(Q+B)/2; DemandImpact=(D+Q+B)/3 when D is available',
                'alternativeScope':'Known rated outputs, all connector types; stat 2/3, unrestricted; same statId excluded; Haversine distance'}
        if len(self._cache)>8:self._cache.clear()
        self._cache[signature]=result
        return result
