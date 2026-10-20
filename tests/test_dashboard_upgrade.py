import copy,os,unittest
from datetime import datetime,timedelta
from unittest.mock import patch
from services.engine import analyze,impact,totals,session_hourly,KST,FORMULA_VERSION
from services.api import Service,ApiError
from services.sample import sample_snapshot
from services.store import Store
from services.worker import normalize_me
class DashboardUpgradeTests(unittest.TestCase):
 def test_new_impact_arithmetic_mean(self): self.assertAlmostEqual(impact(.8,200,400,0),(.8+.5+1)/3)
 def test_score_factors_exposed(self):
  s=sample_snapshot();r=analyze(s)['priorities'][0];self.assertAlmostEqual(r['score'],(r['D']+r['Q']+r['B'])/3);self.assertTrue(0<=r['score']<=1)
 def test_default_radius_and_version(self):
  service=Service(Store(':memory:'));r=service.dispatch('GET','/api/v1/overview',{'mode':'sample'});self.assertEqual(r['radius_m'],500);self.assertEqual(r['formula_version'],FORMULA_VERSION)
 def test_state_counts_missing_power_independent(self):
  s=sample_snapshot();s['stations']=s['stations'][:1];cs=s['stations'][0]['chargers'];cs[0].update(status='MAINTENANCE',power_kw=None);cs[1]['status']='COMM_ERROR';cs[2]['status']='AVAILABLE';r=totals(s['stations'],s['observed_at']);self.assertEqual(r['maintenance_count'],1);self.assertEqual(r['uncertain_count'],1);self.assertEqual(r['normal_count'],1);self.assertEqual(r['missing_power_count'],1);self.assertEqual(sum(r[k] for k in ('normal_count','stopped_count','maintenance_count','uncertain_count')),r['charger_count'])
 def test_neighbour_beyond_district_included(self):
  s=sample_snapshot();s['stations']=s['stations'][:2];a,b=s['stations'];b.update(analysis_target=False,district='다른구',lat=a['lat']+.001,lon=a['lon']);r=analyze(s,500);self.assertEqual(len(r['stations']),1);external=next(x for x in r['map_stations'] if x['id']==b['id']);self.assertIn(a['id'],external['near_target_ids']);self.assertGreater(r['stations'][0]['alternative_kw'],0)
 def test_far_external_not_on_map(self):
  s=sample_snapshot();s['stations']=s['stations'][:2];s['stations'][1].update(analysis_target=False,lat=38.,lon=127.);self.assertEqual(len(analyze(s)['map_stations']),1)
 def test_maintenance_hourly_clipped_and_no_data(self):
  start=datetime(2025,1,1,tzinfo=KST);end=datetime(2026,1,1,tzinfo=KST);self.assertIsNone(session_hourly([],start,end));r=session_hourly([(end-timedelta(minutes=30),end+timedelta(hours=1))],start,end);self.assertEqual(sum(map(sum,r['values'])),30)
 def test_provider_coordinates_used_without_geocoding(self):
  with patch.dict(os.environ,{'ME_MAPPING_VERIFIED':'false'}): s=normalize_me([dict(statId='fixture',chgerId='1',lat='37.572',lng='126.977')],'2026-10-16T00:00:00+00:00')[0]
  self.assertEqual((s['lat'],s['lon']),(37.572,126.977));self.assertEqual(s['chargers'][0]['status'],'UNKNOWN')
 def test_old_formula_runs_rejected(self):
  store=Store(':memory:');service=Service(store);store.put('runs',dict(id='legacy',snapshot=sample_snapshot(),radius_m=500,evaluated_at=service.sample['observed_at'],q95=1000),'legacy')
  with self.assertRaises(ApiError) as e: service.dispatch('POST','/api/v1/simulations',body={'analysis_run_id':'legacy','charger_ids':[]})
  self.assertEqual(e.exception.status,409)
if __name__=='__main__': unittest.main()
