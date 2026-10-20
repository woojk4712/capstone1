import copy,os,unittest
from unittest.mock import patch
from services.api import Service,ApiError
from services.store import Store
from services.sample import sample_snapshot
class MatchingTests(unittest.TestCase):
 def setUp(self):
  self.store=Store(':memory:');self.api=Service(self.store);self.s=sample_snapshot();self.s['mode']='live';self.s['id']='test-live';self.s['stations']=self.s['stations'][:2]
  for s in self.s['stations']: s.update(annual_kwh=None,match_status='unmatched')
  self.store.put('snapshots',self.s,self.s['id']);self.name='원자료 시설';self.demand={self.name:dict(annual_kwh=100000,monthly_kwh=[100000/12]*12,months=list(range(1,13)))}
 def approve(self,sid,status='approved'):
  body=dict(station_id=sid,source_name=self.name,status=status,evidence='주소·좌표·독립 물리 설비 확인 테스트',reviewer='local-test',physical_verified=True,sharing_verified=True,access_verified=True,compatible_verified=True)
  return self.api.dispatch('PATCH','/api/v1/admin/matches/'+sid,body=body,headers={'authorization':'Bearer test-token'})
 def test_review_excluded_then_approved_and_immutable(self):
  sid=self.s['stations'][0]['id']
  with patch.dict(os.environ,{'ADMIN_TOKEN':'test-token'}),patch.object(self.api,'jsonfile',return_value=self.demand):
   before=self.api.dispatch('GET','/api/v1/overview');self.assertFalse(before['priorities']);self.approve(sid,'review_required');self.assertFalse(self.api.dispatch('GET','/api/v1/overview')['priorities']);self.approve(sid);after=self.api.dispatch('GET','/api/v1/overview');self.assertTrue(after['priorities']);self.assertNotEqual(before['snapshot_id'],after['snapshot_id']);frozen=self.api.dispatch('GET','/api/v1/overview',dict(analysis_run_id=before['analysis_run_id']));self.assertFalse(frozen['priorities']);self.assertIsNone(self.store.get('snapshots','test-live')['stations'][0]['annual_kwh'])
 def test_ambiguous_source_cannot_be_approved_twice(self):
  with patch.dict(os.environ,{'ADMIN_TOKEN':'test-token'}),patch.object(self.api,'jsonfile',return_value=self.demand):
   self.approve(self.s['stations'][0]['id'])
   with self.assertRaises(ApiError) as e: self.approve(self.s['stations'][1]['id'])
   self.assertEqual(e.exception.status,409)
 def test_evidence_required(self):
  with patch.dict(os.environ,{'ADMIN_TOKEN':'test-token'}),patch.object(self.api,'jsonfile',return_value=self.demand):
   with self.assertRaises(ApiError) as e: self.api.dispatch('PATCH','/api/v1/admin/matches/'+self.s['stations'][0]['id'],body=dict(source_name=self.name,status='approved'),headers={'authorization':'Bearer test-token'})
   self.assertEqual(e.exception.status,422)
if __name__=='__main__': unittest.main()
