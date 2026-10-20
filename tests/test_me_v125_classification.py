import unittest
from backend.app.settings import Settings, ROOT
from backend.app.services.me_classification import load_contract
from backend.app.services.me_api import classifications, model

class MEGuideTests(unittest.TestCase):
    def setUp(self):
        self.settings=Settings({}, me_contract=load_contract(ROOT))

    def test_original_official_source_enables_status_only(self):
        types,states=classifications(self.settings)
        self.assertTrue(self.settings.me_contract.get('status_verified'))
        self.assertEqual(types,set())
        self.assertEqual(states['4'],'STOPPED')
        self.assertEqual(states['5'],'MAINTENANCE')
        self.assertEqual(states['9'],'UNKNOWN')
        self.assertEqual(states['6'],'UNKNOWN')

    def test_raw_codes_and_unknown_are_preserved_without_invented_meaning(self):
        for raw in ('0','1','2','3','4','5','6','9','future'):
            result=model({'stat':raw,'chgerType':'11','delYn':'N'},self.settings,'2026-10-17')
            self.assertEqual(result['stat'],raw)
            self.assertTrue(result['statusClassificationVerified'])
            self.assertFalse(result['chargerTypeClassificationVerified'])
            self.assertEqual(result['recovery_review_candidate'],raw=='4')
        self.assertEqual(model({'stat':'6'},self.settings,'now')['status_label'],'예약중')

    def test_stale_and_deleted_are_not_recovery_candidates(self):
        self.assertFalse(model({'stat':'4','delYn':'N'},self.settings,'then',fresh=False)['recovery_review_candidate'])
        self.assertFalse(model({'stat':'4','delYn':'Y'},self.settings,'now')['recovery_review_candidate'])
        self.assertEqual(model({'stat':'2','chgerType':'08'},self.settings,'now')['charging_speed'],'SLOW')
        self.assertEqual(model({'stat':'2','chgerType':'11'},self.settings,'now')['charging_speed'],'UNKNOWN')
