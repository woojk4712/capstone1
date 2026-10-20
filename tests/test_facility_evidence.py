import unittest
from backend.app.facility_matching import address_key, physical_address, bridge_candidates


class PhysicalAddressTests(unittest.TestCase):
    def test_city_spacing_details_and_numbered_roads(self):
        self.assertEqual(address_key('서울 노원구 노해로 437(노원구청) 지상1층'),address_key('서울특별시 노원구 노해로 437'))
        self.assertEqual(address_key('서울시 동대문구 망우로 18나길 20 주차장'),address_key('서울특별시 동대문구 망우로18나길 20'))
        self.assertIsNotNone(physical_address('서울특별시 은평구 진관2로 15-40'))

    def test_physical_distinctions_are_preserved(self):
        for a,b in [('서울특별시 노원구 노해로 437','서울특별시 노원구 노해로 438'),
                    ('서울특별시 송파구 송파대로 지하6','서울특별시 송파구 송파대로 6'),
                    ('서울특별시 중랑구 망우동 산 56','서울특별시 중랑구 망우동 56'),
                    ('서울특별시 성동구 동일로43길 13','서울특별시 성동구 동일로 43')]:
            self.assertNotEqual(address_key(a),address_key(b))

    def test_unique_address_bridge_and_multiple_ids_hold(self):
        f={'normalized_name':'공식시설','address':'서울시 강남구 테스트로 1','district':'강남구'}
        d={'statId':'A','statNm':'다른제공표기','addr':'서울특별시 강남구 테스트로 1'}
        candidates,reason=bridge_candidates(f,[d])
        self.assertEqual([r['statId'] for r in candidates],['A'])
        self.assertEqual(reason,'unique_registry_physical_address')
        candidates,reason=bridge_candidates(f,[d,dict(d,statId='B')])
        self.assertEqual(len(candidates),2)
        self.assertEqual(reason,'multiple_d3_stat_ids_at_address')

    def test_name_alone_district_conflict_and_missing_registry_address_never_approve(self):
        f={'normalized_name':'공식시설','address':'서울시 강남구 테스트로 1','district':'강남구'}
        d={'statId':'A','statNm':'공식시설','addr':'서울특별시 강남구 다른로 2'}
        self.assertEqual(bridge_candidates(f,[d])[0],[])
        self.assertEqual(bridge_candidates(dict(f,district='서초구'),[d])[1],'registry_district_conflict')
        self.assertEqual(bridge_candidates(dict(f,address='주소 확인 필요'),[d])[1],'address_not_structured')
