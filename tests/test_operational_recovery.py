import unittest
from datetime import datetime,timedelta
from pathlib import Path
from types import SimpleNamespace
from tests.test_operational_view import OperationalViewTests
from backend.app.operational_recovery import OperationalRecovery
from backend.app.operational_view import ObservationChanged


class OperationalRecoveryTests(OperationalViewTests):
    def recovery(self,core=None):
        path=Path(self.temp.name)/'analysis';path.touch()
        analysis=SimpleNamespace(path=path,stations=lambda **kw:{'items':core or [],'last_success_at':self.external.storage.state('ME')['last_success_at']})
        return OperationalRecovery(self.view,analysis)

    def test_noncore_stopped_included_qb_separate_d_optional(self):
        r=self.recovery().ranking()['items'][0]
        self.assertFalse(r['d1Connected']);self.assertIsNone(r['D'])
        self.assertAlmostEqual(r['Q'],50/180);self.assertEqual(r['B'],1)
        self.assertAlmostEqual(r['operationalImpact'],(50/180+1)/2)
        core=[{'statId':'S','analysis_ready':True,'annualFastKwh2025':100}]
        r=self.recovery(core).ranking()['items'][0]
        self.assertEqual(r['D'],.5)
        self.assertAlmostEqual(r['demandImpact'],(.5+50/180+1)/3)

    def test_network_radius_same_station_exclusion_and_missing_unit_retention(self):
        extra=[dict(self.rows[0],statId='NEAR',lat='37.501',output='100'),
               dict(self.rows[0],statId='FAR',lat='37.507',output='200'),
               dict(self.rows[0],statId='RESTRICTED',lat='37.501',limitYn='Y'),
               dict(self.rows[1],chgerId='missing',output='')]
        self.external.storage.save_me(self.rows+extra,self.new_stamp(),200)
        service=self.recovery();small=service.ranking(500);large=service.ranking(1000)
        r=next(r for r in small['items'] if r['chgerId']=='2')
        self.assertEqual(r['A'],100);self.assertEqual(large['items'][0]['A'],300)
        self.assertEqual(small['count'],2);self.assertEqual(small['selectableCount'],1)
        self.assertEqual(small['diagnostics']['exclusionReasons'],{'missing_output':1})
        self.assertEqual(r['networkRestricted'],1)

    def new_stamp(self):
        return (datetime.fromisoformat(self.external.storage.state('ME')['last_success_at'])+timedelta(microseconds=1)).isoformat()

    def test_pinned_observation_survives_next_collection_without_writes(self):
        first=self.recovery().ranking();stamp=first['observationAt']
        self.external.storage.save_me([dict(c,stat='2') for c in self.rows],self.new_stamp(),200)
        original=self.external.storage.rows()
        with self.external.storage.connection() as db:count=db.execute('SELECT COUNT(*) FROM status_snapshots').fetchone()[0]
        result=self.view.simulate(['ME:S:2'],['S'],True,stamp)
        self.assertEqual(result['recoveredKw'],50);self.assertEqual(result['observationAt'],stamp)
        self.assertEqual(original,self.external.storage.rows())
        with self.external.storage.connection() as db:self.assertEqual(count,db.execute('SELECT COUNT(*) FROM status_snapshots').fetchone()[0])
        with self.assertRaises(ObservationChanged):self.view.inventory('unknown')
