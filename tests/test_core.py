import copy,json,math,os,tempfile,unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
from urllib.parse import parse_qs,urlsplit
from services.engine import *
from services.sample import sample_snapshot
from services.api import Service,ApiError
from services.store import Store,now
from services.worker import fetch_pages,ProviderError,normalize_me,collect_once,cross_validate
class EngineTests(unittest.TestCase):
 def setUp(self):
  self.s=sample_snapshot(); self.at=self.s['observed_at']; r=analyze(self.s); self.run=dict(radius_m=1000,q95=r['q95'],evaluated_at=self.at); self.ids=[r['charger_id'] for r in r['priorities']]
 def test_examples(self):
  for alt,expected in [(0,40),(200,20),(600,10)]: self.assertAlmostEqual(legacy_impact(.8,200,400,alt),expected)
 def test_score_monotonicity(self):
  self.assertLessEqual(impact(.5,100,400,0),impact(.8,100,400,0));self.assertGreaterEqual(impact(.8,100,400,0),impact(.8,100,400,600))
 def test_empty_selection(self):
  r=simulate(self.s,self.run,[]);self.assertEqual(r['recovered_kw'],0);self.assertEqual(r['before'],r['after'])
 def test_duplicate_selection(self):
  a=simulate(self.s,self.run,[self.ids[0]]);b=simulate(self.s,self.run,[self.ids[0]]*3);self.assertEqual(a,b)
 def test_capacity_conservation_all(self):
  r=simulate(self.s,self.run,self.ids);a=r['after']['totals'];b=r['before']['totals'];self.assertEqual(a['total_kw'],b['total_kw']);self.assertEqual(a['uncertain_kw'],b['uncertain_kw']);self.assertEqual(a['normal_kw']-b['normal_kw'],b['stopped_kw']-a['stopped_kw']);self.assertGreaterEqual(a['stopped_kw'],0)
 def test_source_isolation(self):
  saved=copy.deepcopy(self.s);simulate(self.s,self.run,self.ids);self.assertEqual(saved,self.s)
 def test_invalid_selection(self):
  with self.assertRaises(ValueError): simulate(self.s,self.run,['invalid'])
 def test_stale_excluded(self):
  c=next(c for s in self.s['stations'] for c in s['chargers'] if c['id']==self.ids[0]);c['ttl_minutes']=0;c['last_verified_at']='2020-01-01T00:00:00+00:00';r=analyze(self.s);self.assertNotIn(c['id'],[x['charger_id'] for x in r['priorities']]);self.assertEqual(state(c,self.at),'UNKNOWN')
 def test_missing_power_null_score(self):
  self.s['stations'][0]['chargers'][0]['power_kw']=None;r=analyze(self.s);row=next(r for r in r['held'] if r['station_id']==self.s['stations'][0]['id']);self.assertIsNone(row['score']);self.assertTrue(row['reasons'])
 def test_unapproved_excluded(self):
  self.s['stations'][0]['match_status']='review_required';r=analyze(self.s);self.assertFalse(any(r['station_id']==self.s['stations'][0]['id'] for r in r['priorities']))
 def test_self_exclusion_and_boundary(self):
  a=copy.deepcopy(self.s['stations'][0]);a.update(lat=0.,lon=0.);b=copy.deepcopy(a);b['id']='other';b['lon']=math.degrees(1000/6371008.8);b['chargers'][0]['status']='AVAILABLE';radius=distance(a,b)
  self.assertAlmostEqual(radius,1000,places=7);self.assertEqual(alternatives(a,[a],1000,self.at),[]);self.assertTrue(alternatives(a,[a,b],1000,self.at));self.assertEqual(alternatives(a,[a,b],999.99,self.at),[])
 def test_physical_dedup(self):
  a=copy.deepcopy(self.s['stations'][0]);c=copy.deepcopy(a['chargers'][0]);c['physical_unit_id']='unit';a['chargers'][0]['physical_unit_id']='unit';a['chargers'].append(c);self.assertEqual(totals([a],self.at),totals([self.s['stations'][0]],self.at))
 def test_neighbour_scores_recalculated(self):
  s=copy.deepcopy(self.s);s['stations']=s['stations'][:2];s['stations'][1]['lat']=s['stations'][0]['lat']+.001;s['stations'][1]['lon']=s['stations'][0]['lon'];s['stations'][1]['chargers'][0]['status']='STOPPED';r=analyze(s);run=dict(radius_m=1000,q95=r['q95'],evaluated_at=s['observed_at']);target=s['stations'][0]['chargers'][0]['id'];other=s['stations'][1]['chargers'][0]['id'];out=simulate(s,run,[target]);before=next(x for x in out['before']['priorities'] if x['charger_id']==other);after=next(x for x in out['after']['priorities'] if x['charger_id']==other);self.assertLess(after['score'],before['score'])
 def test_shared_unknown_held(self):
  self.s['stations'][0]['chargers'][0]['sharing_verified']=False;r=analyze(self.s);self.assertTrue(any('공유출력' in ' '.join(x['reasons']) for x in r['held']))
 def test_network_incomplete_held(self):
  self.s['network_complete']=False;self.assertEqual(analyze(self.s)['priorities'],[])
class MaintenanceTests(unittest.TestCase):
 def test_midnight_year_boundary(self):
  a=datetime(2025,12,31,23,30,tzinfo=KST);b=datetime(2026,1,1,0,30,tzinfo=KST);self.assertEqual(overlap_minutes(a,b,a,datetime(2026,1,1,tzinfo=KST)),30)
 def test_halfopen(self):
  a=datetime(2025,1,1,tzinfo=KST);self.assertEqual(overlap_minutes(a,a+timedelta(hours=1),a+timedelta(hours=1),a+timedelta(hours=2)),0)
 def test_concurrent_minutes(self):
  a=datetime(2025,1,1,tzinfo=KST);self.assertEqual(sum(overlap_minutes(a,a+timedelta(hours=1),a,a+timedelta(hours=1)) for _ in range(2)),120)
 def test_coverage_and_history_hold(self):
  r=maintenance([],None,False,0,60,datetime(2025,1,1,tzinfo=KST),datetime(2026,1,1,tzinfo=KST));self.assertEqual(r['candidates'],[]);self.assertEqual(len(r['reasons']),3)
 def test_sample_threshold_and_nonoverlap(self):
  start=datetime(2025,1,1,tzinfo=KST);end=datetime(2026,1,1,tzinfo=KST);days=[(start+timedelta(days=i)).date().isoformat() for i in range(200)];r=maintenance([],days,True,0,120,start,end);self.assertEqual(len(r['candidates']),3);self.assertEqual([x['start_minute'] for x in r['candidates']],[0,120,240])
class CollectorTests(unittest.TestCase):
 def payload(self,page,total,items): return json.dumps(dict(response=dict(header=dict(resultCode='00'),body=dict(totalCount=total,pageNo=page,items=dict(item=items))))).encode()
 def test_multiple_pages(self):
  def transport(url):
   p=int(parse_qs(urlsplit(url).query)['pageNo'][0]);return self.payload(p,3,[{'id':1},{'id':2}] if p==1 else [{'id':3}])
  r,h,raw=fetch_pages('ME','https://example.test','secret',transport=transport,sleeper=lambda _:None,page_size=2);self.assertEqual(len(r),3);self.assertEqual(len(h),2)
 def test_retry_no_duplicate(self):
  attempts=[]
  def transport(url):
   attempts.append(1)
   if len(attempts)==1: raise TimeoutError()
   return self.payload(1,1,[{'id':1}])
  rows,_,_=fetch_pages('ME','https://example.test','key',transport=transport,sleeper=lambda _:None);self.assertEqual(len(rows),1);self.assertEqual(len(attempts),2)
 def test_partial_failure_not_published(self):
  import tempfile
  from pathlib import Path
  from backend.app.storage import Storage
  from backend.app.core import ExternalService
  from backend.app.settings import Settings
  from backend.app.services.transport import ProviderError as NewError
  with tempfile.TemporaryDirectory() as tmp:
   service=ExternalService(Settings({}),Storage(Path(tmp)/'test.sqlite'))
   with patch.object(service,'diagnose',return_value={}),patch('backend.app.core.MEAPI.fetch',side_effect=NewError('incomplete_collection')): r=collect_once(service)
   self.assertEqual(service.storage.rows(),[]);self.assertEqual(r['providers']['ME']['error']['kind'],'incomplete_collection')
 def test_auth_error_classification(self):
  raw=b'<response><header><resultCode>30</resultCode></header></response>'
  with self.assertRaises(ProviderError) as c: fetch_pages('ME','https://example.test','key',transport=lambda _:raw,sleeper=lambda _:None)
  self.assertEqual(c.exception.kind,'authentication')
 def test_quota_classification(self):
  raw=b'<response><header><resultCode>22</resultCode></header></response>'
  with self.assertRaises(ProviderError) as c: fetch_pages('ME','https://example.test','key',transport=lambda _:raw,sleeper=lambda _:None)
  self.assertEqual(c.exception.kind,'quota')
 def test_missing_page(self):
  with self.assertRaises(ProviderError): fetch_pages('ME','https://example.test','key',transport=lambda _:self.payload(1,10,[]),sleeper=lambda _:None)
 def test_unverified_mapping_unknown(self):
  with patch.dict(os.environ,{'ME_MAPPING_VERIFIED':'false'}): s=normalize_me([dict(statId='A',chgerId='1',stat='2',statUpdDt='20250101120000')],now())
  self.assertEqual(s[0]['chargers'][0]['status'],'UNKNOWN');self.assertIsNone(s[0]['chargers'][0]['last_verified_at'])
 def test_duplicate_identifier_rejected(self):
  row=dict(statId='A',chgerId='1')
  with self.assertRaises(ProviderError): normalize_me([row,row],now())
 def test_kepco_failure_does_not_block_me(self):
  import tempfile
  from pathlib import Path
  from backend.app.storage import Storage
  from backend.app.core import ExternalService
  from backend.app.settings import Settings
  from backend.app.services.transport import ProviderError as NewError
  with tempfile.TemporaryDirectory() as tmp:
   service=ExternalService(Settings({}),Storage(Path(tmp)/'test.sqlite'))
   with patch.object(service,'diagnose',return_value={}),patch('backend.app.core.MEAPI.fetch',return_value=[dict(statId='A',chgerId='1',statNm='A')]),patch('backend.app.core.KEPCOAPI.fetch',side_effect=NewError('api_authentication_error')): r=collect_once(service)
   self.assertEqual(len(service.storage.rows()),1);self.assertEqual(r['providers']['KEPCO']['error']['kind'],'api_authentication_error')
 def test_cross_validation_time_gap(self):
  r=cross_validate([dict(id='a',status='AVAILABLE',source_updated_at='2025-01-01T00:00:00+09:00')],[dict(id='b',status='2',at='2025-01-01T00:10:00+09:00')],{'a':'b'},{'id':'id','status':'status','updated_at':'at'},{'2':'AVAILABLE'});self.assertEqual(r[0]['result'],'시간차로 비교 불가')
class ApiTests(unittest.TestCase):
 def setUp(self): self.api=Service(Store(':memory:'))
 def test_explicit_mode(self):
  with self.assertRaises(ApiError) as e: self.api.dispatch('GET','/api/v1/overview')
  self.assertEqual(e.exception.status,503)
 def test_metadata_and_simulation(self):
  r=self.api.dispatch('GET','/api/v1/overview',{'mode':'sample'});ids=[r['priorities'][0]['charger_id']]*2;s=self.api.dispatch('POST','/api/v1/simulations',body=dict(analysis_run_id=r['analysis_run_id'],charger_ids=ids));self.assertEqual(len(s['charger_ids']),1);self.assertEqual(s['snapshot_id'],r['snapshot_id']);self.assertGreater(s['recovered_kw'],0)
 def test_invalid_radius(self):
  with self.assertRaises(ApiError) as e: self.api.dispatch('GET','/api/v1/overview',dict(mode='sample',radius_m='800'))
  self.assertEqual(e.exception.status,422)
 def test_invalid_maintenance_duration(self):
  with self.assertRaises(ApiError) as e: self.api.dispatch('GET','/api/v1/stations/SAMPLE-001/maintenance',dict(mode='sample',duration_minutes='90'))
  self.assertEqual(e.exception.status,422)
 def test_run_radius_conflict(self):
  r=self.api.dispatch('GET','/api/v1/overview',dict(mode='sample'))
  with self.assertRaises(ApiError) as e: self.api.dispatch('GET','/api/v1/priorities',dict(mode='sample',radius_m='1000',analysis_run_id=r['analysis_run_id']))
  self.assertEqual(e.exception.status,409)
 def test_station_filters(self):
  r=self.api.dispatch('GET','/api/v1/stations',dict(mode='sample',district='종로구',page_size='1'));self.assertEqual(len(r['items']),1);self.assertEqual(r['total'],2)
 def test_missing_station(self):
  with self.assertRaises(ApiError) as e: self.api.dispatch('GET','/api/v1/stations/nope',dict(mode='sample'))
  self.assertEqual(e.exception.status,404)
 def test_admin_requires_auth(self):
  with self.assertRaises(ApiError) as e: self.api.dispatch('PATCH','/api/v1/admin/matches/a',body={})
  self.assertEqual(e.exception.status,401)
if __name__=='__main__': unittest.main()
