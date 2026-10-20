"""Read-only scenario validation with isolated observations, never real confirmations."""
import tempfile
import unittest
from datetime import datetime,timedelta
from pathlib import Path
from backend.app.core import ExternalService
from backend.app.settings import Settings
from backend.app.storage import Storage, now
from backend.app.operational_view import OperationalView


class OperationalViewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        settings = Settings({'ME_MAPPING_VERIFIED':'true','ME_FAST_TYPES':'["04"]',
                             'ME_STATUS_MAP':'{"2":"AVAILABLE","4":"STOPPED","5":"MAINTENANCE"}'})
        self.external = ExternalService(settings, Storage(Path(self.temp.name)/'external.sqlite'))
        self.rows = [dict(statId='S',chgerId=str(i),statNm='독립 검증시설',addr='서울특별시 강남구 검증로',
                          lat='37.5',lng='127',delYn='N',limitYn='N',chgerType='04',output=str(power),stat=stat)
                     for i,power,stat in [(1,100,'2'),(2,50,'4'),(3,30,'5')]]
        self.external.storage.save_me(self.rows, now(), 200)
        self.view = OperationalView(self.external)

    def tearDown(self):
        self.temp.cleanup()

    def test_output_conservation_and_original_database_unchanged(self):
        original = self.external.storage.rows()
        result = self.view.simulate(['ME:S:2'], ['S'])
        self.assertEqual(result['before']['normalKw'],100)
        self.assertEqual(result['after']['normalKw'],150)
        self.assertEqual(result['after']['stoppedKw'],0)
        self.assertEqual(result['after']['stoppedCount'],0)
        self.assertEqual(result['recoveryRate'],50)
        self.assertEqual(result['before']['maintenanceKw'],result['after']['maintenanceKw'])
        self.assertEqual(original,self.external.storage.rows())

    def test_only_stopped_positive_power_in_selected_seoul_scope(self):
        for ids, scope in [(['ME:S:1'],['S']),(['ME:S:3'],['S']),(['ME:S:2'],[]),([],['NONEXISTENT'])]:
            with self.assertRaises(ValueError): self.view.simulate(ids,scope)

    def test_stale_requires_explicit_replay_and_zero_normal_rate_is_null(self):
        self.external.is_fresh=lambda:False
        with self.assertRaises(ValueError): self.view.simulate(['ME:S:2'],['S'])
        result=self.view.simulate(['ME:S:2'],['S'],True)
        self.assertTrue(result['stale'])
        self.assertTrue(result['replay'])
        # A new observation must have a distinct identity, even on a coarse Windows clock.
        stamp=(datetime.fromisoformat(self.external.storage.state('ME')['last_success_at'])+timedelta(microseconds=1)).isoformat()
        self.external.storage.save_me(self.rows[1:],stamp,200)
        self.assertIsNone(self.view.simulate(['ME:S:2'],['S'],True)['recoveryRate'])

    def test_nonseoul_deleted_invalid_coordinates_are_excluded(self):
        rows=[dict(self.rows[0],statId='NONSEOUL',addr='경기도 성남시'),
              dict(self.rows[0],statId='DELETED',delYn='Y'),
              dict(self.rows[0],statId='BADCOORD',lat='')]
        self.external.storage.save_me(self.rows+rows,now(),200)
        self.assertEqual([s['statId'] for s in self.view.stations()['items']],['S'])
