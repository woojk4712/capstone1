import copy,unittest
from services.engine import analyze
from services.sample import sample_snapshot
class NetworkScopeTests(unittest.TestCase):
 def test_external_network_not_counted_as_target(self):
  s=sample_snapshot();s['stations']=s['stations'][:2];target=s['stations'][0];external=s['stations'][1];external['analysis_target']=False;external['lat']=target['lat']+.001;external['lon']=target['lon'];r=analyze(s)
  self.assertEqual(len(r['stations']),1);self.assertEqual(r['totals']['charger_count'],len(target['chargers']));self.assertGreater(r['stations'][0]['alternative_kw'],0)
 def test_external_network_demand_does_not_change_q95(self):
  s=sample_snapshot();s['stations']=s['stations'][:2];s['stations'][1]['analysis_target']=False;q=analyze(s)['q95'];s['stations'][1]['annual_kwh']=1e12;self.assertEqual(analyze(s)['q95'],q)
if __name__=='__main__': unittest.main()
