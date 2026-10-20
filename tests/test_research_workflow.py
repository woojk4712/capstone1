"""Numerical fixtures in temporary SQLite only, never production confirmations."""
import csv
import json
import tempfile
import unittest
from pathlib import Path
from backend.app.research import ResearchService, average_ranks, address_key, BRIDGE
from backend.app.settings import Settings
from backend.app.storage import Storage, now
from backend.app.core import ExternalService

class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        settings=Settings({'ME_MAPPING_VERIFIED':'true','ME_FAST_TYPES':'["04"]','ME_STATUS_MAP':'{"2":"AVAILABLE","3":"CHARGING","4":"STOPPED","5":"MAINTENANCE","9":"UNKNOWN"}'})
        storage=Storage(self.root/'external.sqlite');self.external=ExternalService(settings,storage)
        rows=[]
        for sid,name,output,stat,lon in [('A','가시설',100,'4',127.),('B','나시설',100,'2',127.0001),('C','다시설',200,'4',127.0002)]:
            rows.append(dict(statId=sid,chgerId='01',statNm=name,addr='서울특별시 강남구 테스트로 '+str(ord(sid)-64),lat='37.5',lng=str(lon),chgerType='04',output=str(output),stat=stat,delYn='N',limitYn='N',useTime='24시간 이용가능'))
        rows.append(dict(rows[0],chgerId='02',stat='2'))
        storage.save_me(rows,now(),200)
        self.service=ResearchService(self.external,self.root/'analysis.sqlite')
        self.source={'available':True,'sha256':'ISOLATED_D1_FIXTURE','fast_station_names':3}
        self.service.prepare_d1=lambda:self.source
        self.service.prepare_d2=lambda:{'available':False}
        self.service.find_source=lambda filename:self.root/BRIDGE if filename==BRIDGE else None
        with self.service.db() as db:
            db.execute('INSERT INTO analysis_meta VALUES (?,?)',('d1',json.dumps(self.source)))
            for n,energy in [('가시설',100),('나시설',200),('다시설',200)]:
                db.execute('INSERT INTO d1_demand VALUES (?,?,?,?,?)',(n,n,energy,json.dumps([energy]+[None]*11),1))
        with (self.root/BRIDGE).open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=['CHARG_STTN','ADDR','CHARG_ID','CHARG_TYPE','CHARG_CPCT','SGG']);w.writeheader()
            for r in rows:w.writerow({'CHARG_STTN':r['statNm'],'ADDR':r['addr'],'CHARG_ID':int(r['chgerId']),'CHARG_TYPE':'DC콤보','CHARG_CPCT':'급속('+r['output']+'kW단독)','SGG':'강남구'})
        self.service.prepare_all()
        with self.service.db() as db:db.execute('INSERT OR REPLACE INTO analysis_meta VALUES (?,?)',('d1_types',json.dumps({n:['급속'] for n in ('가시설','나시설','다시설')})))

    def tearDown(self):self.tmp.cleanup()

    def test_registry_address_normalization_and_dynamic_confirmed_growth(self):
        before=self.service.stations()
        self.assertEqual(before['total'],3)
        with (self.root/BRIDGE).open(encoding='utf-8-sig',newline='') as f:
            reader=csv.DictReader(f);fields=reader.fieldnames;rows=list(reader)
        for row in rows:
            if row['CHARG_STTN']=='가시설':row['ADDR']='서울 강남구 테스트로 1 (시설 입구) 지상1층'
        raw=[r for r,_ in self.external.storage.rows()]
        d=dict(raw[0],statId='D',chgerId='01',statNm='추가시설',addr='서울특별시 강남구 테스트로 4',lng='127.0003')
        self.external.storage.save_me(raw+[d],now(),200)
        rows.append({'CHARG_STTN':'추가시설','ADDR':d['addr'],'CHARG_ID':'1','CHARG_TYPE':'DC콤보','CHARG_CPCT':'급속(100kW단독)','SGG':'강남구'})
        with (self.root/BRIDGE).open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
        with self.service.db() as db:
            db.execute('INSERT INTO d1_demand VALUES (?,?,?,?,?)',('추가시설','추가시설',300,json.dumps([300]+[None]*11),1))
        self.service.prepare_all()
        self.assertEqual(self.service.stations()['total'],4)
        self.assertEqual(self.service.match_summary()['confirmed_auto'],4)
        addition=next(r for r in self.service.match_rows() if r['d1_station_name']=='추가시설')
        self.assertTrue(addition['match_evidence'])
        self.assertIn('address',addition['confidence_reason'])

    def test_same_stat_id_with_conflicting_coordinates_remains_review(self):
        raw=[dict(r,lat='37.8') if r['statId']=='A' and r['chgerId']=='02' else r for r,_ in self.external.storage.rows()]
        self.external.storage.save_me(raw,now(),200)
        self.service.prepare_all()
        a=next(r for r in self.service.match_rows() if r['candidate_stat_id']=='A')
        self.assertEqual(a['match_status'],'review')
        self.assertEqual(a['hold_reason_code'],'coordinate_conflict')

    def test_exact_name_address_bridge_confirms_and_charger_evidence_enables_analysis(self):
        self.assertEqual(self.service.match_summary()['confirmed_auto'],3)
        self.assertTrue(all(s['analysis_ready'] for s in self.service.stations()['items']))
        self.assertEqual(self.service.quality()['facilityConnectionRate'],1)
        self.assertEqual(self.service.quality()['kwhConnectionRate'],1)

    def test_tied_average_rank_and_p_over_p_plus_a(self):
        self.assertEqual(average_ranks({'A':100,'B':200,'C':200}),{'A':0,'B':.75,'C':.75})
        data=self.service.overview();a=next(r for r in data['priorities'] if r['statId']=='A')
        self.assertEqual(a['D'],0);self.assertEqual(a['Q'],.5);self.assertAlmostEqual(a['B'],2/3)
        self.assertAlmostEqual(a['score'],(0+.5+2/3)/3)
        self.assertEqual([r['statId'] for r in data['priorities']],['C','A'])
        self.assertAlmostEqual(next(r for r in self.service.overview(weight='power')['priorities'] if r['statId']=='A')['score'],.25*0+.5*.5+.25*2/3)

    def test_simulation_conservation_rate_and_no_original_mutation(self):
        original=self.external.storage.rows();result=self.service.simulate(['ME:A:01'])
        self.assertEqual(result['before']['normalKw'],200);self.assertEqual(result['after']['normalKw'],300)
        self.assertEqual(result['recoveredKw'],100);self.assertEqual(result['recoveryRate'],50)
        self.assertEqual(result['before']['stoppedKw']-result['after']['stoppedKw'],100)
        self.assertEqual(result['before']['maintenanceKw'],result['after']['maintenanceKw'])
        self.assertEqual(self.external.storage.rows(),original)
        all_result=self.service.simulate(['ME:A:01','ME:C:01'])
        self.assertEqual(all_result['after']['stoppedCount'],0)
        self.assertEqual(all_result['after']['highImpactUnrestored'],0)

    def test_inspection_is_not_a_recovery_candidate_and_stale_never_creates_rank(self):
        rows=[dict(r,stat='5') if r['statId']=='C' else r for r,t in self.external.storage.rows()]
        self.external.storage.save_me(rows,now(),200)
        self.assertFalse(any(r['statId']=='C' for r in self.service.overview()['priorities']))
        with self.assertRaises(ValueError):self.service.simulate(['ME:C:01'])
        self.external.is_fresh=lambda:False
        result=self.service.overview()
        self.assertEqual(result['priorities'],[]);self.assertEqual(result['potential'],[])
        self.assertTrue(result['held'])
        self.assertIsNone(self.service.simulate([],hypothetical=True)['recoveredKw'])
        replay=self.service.overview(replay=True)
        self.assertTrue(replay['stale']);self.assertTrue(replay['replay'])
        self.assertTrue(replay['potential'])
        self.assertTrue(self.service.simulate(['ME:A:02'],hypothetical=True,replay=True)['warning'].startswith('과거 관측 재현'))

    def test_zero_normal_power_has_null_recovery_rate(self):
        self.external.storage.save_me([dict(r,stat='4') for r,t in self.external.storage.rows()],now(),200)
        result=self.service.simulate(['ME:A:01'])
        self.assertEqual(result['before']['normalKw'],0)
        self.assertEqual(result['recoveredKw'],100)
        self.assertIsNone(result['recoveryRate'])

    def test_unknown_nearby_type_cannot_be_an_exact_final_recovery_rank(self):
        rows=[r for r,t in self.external.storage.rows()]
        rows.append(dict(rows[1],statId='UNKNOWN_NETWORK',chgerType='future',stat='2'))
        self.external.storage.save_me(rows,now(),200)
        data=self.service.overview()
        self.assertEqual(data['priorities'],[])
        self.assertTrue(all(r['scoreIsUpperBound'] for r in data['potential']))
        self.assertTrue(any('상한' in reason for r in data['held'] for reason in r['reasons']))

    def test_manual_hold_persists_and_manual_confirm_updates_immediately(self):
        self.service.review('가시설','A','hold','공식 주소와 현장 시설의 구획이 달라 추가 검토')
        self.assertEqual(self.service.match_summary()['confirmed'],2)
        self.assertEqual(self.service.stations()['total'],2)
        self.service.prepare_all()
        self.assertEqual(self.service.match_summary()['confirmed'],2)
        self.service.review('가시설','A','confirm','공식 시설대장 주소 및 충전기 식별자 직접 비교 완료')
        self.assertEqual(self.service.match_summary()['confirmed_manual'],1)
        self.assertEqual(self.service.stations()['total'],3)

    def test_ambiguous_duplicate_stat_id_is_not_auto_confirmed(self):
        rows=[r for r,t in self.external.storage.rows()]
        rows.append(dict(rows[0],statId='AX'))
        self.external.storage.save_me(rows,now(),200);self.service.prepare_all()
        self.assertEqual(self.service.match_summary()['confirmed_auto'],2)
        self.assertFalse(any(s['statId'] in ('A','AX') for s in self.service.stations()['items']))

    def test_maintenance_observed_days_starts_boundaries_and_mixed_hold(self):
        with self.service.db() as db:
            db.execute('INSERT OR REPLACE INTO analysis_meta VALUES (?,?)',('d2',json.dumps({'available':True})))
            for i,day in enumerate(('2025-01-06','2025-01-13','2025-01-20')):
                db.execute('INSERT INTO d2_sessions VALUES (?,?,?,?,?,?,?,?)',(i,'가시설','가시설',day+'T03:00:00',day+'T04:00:00','10','[]','{}'))
        result=self.service.maintenance('A')
        self.assertEqual(result['validDaysByWeekday'],[3,0,0,0,0,0,0])
        self.assertEqual(result['heatmap'][0][3],1)
        self.assertTrue(all(c['validDays']==3 for c in result['oneHour']))
        self.assertTrue(result['oneHour']);self.assertTrue(result['twoHour'])
        self.assertEqual(result['oneHour'][0]['avg_active_at_window_start'],0)
        with self.service.db() as db:db.execute('INSERT OR REPLACE INTO analysis_meta VALUES (?,?)',('d1_types',json.dumps({'가시설':['급속','완속']})))
        self.assertEqual(self.service.maintenance('A')['status'],'HOLD_MIXED')

    def test_address_core_preserves_distinct_building_numbers(self):
        self.assertEqual(address_key('서울시 강남구 테스트로 12 (건물명)'),address_key('서울특별시 강남구 테스트로 12'))
        self.assertNotEqual(address_key('서울특별시 강남구 테스트로 12'),address_key('서울특별시 강남구 테스트로 12-1'))

    def test_cross_midnight_two_hour_window_requires_both_observed_dates(self):
        rows=[dict(r,useTime='23:00~02:00') if r['statId']=='A' else r for r,t in self.external.storage.rows()]
        self.external.storage.save_me(rows,now(),200)
        with self.service.db() as db:
            db.execute('INSERT OR REPLACE INTO analysis_meta VALUES (?,?)',('d2',json.dumps({'available':True})))
            for i,day in enumerate(('2025-01-06','2025-01-13','2025-01-20')):
                db.execute('INSERT INTO d2_sessions VALUES (?,?,?,?,?,?,?,?)',(i,'가시설','가시설',day+'T03:00:00',day+'T04:00:00','10','[]','{}'))
            for i,day in enumerate(('2025-01-07','2025-01-14'),10):
                db.execute('INSERT INTO d2_sessions VALUES (?,?,?,?,?,?,?,?)',(i,'가시설','가시설',day+'T00:30:00',day+'T01:00:00','10','[]','{}'))
        result=self.service.maintenance('A')
        crossing=next(c for c in result['twoHour'] if c['weekday']==0 and c['startMinute']==1380)
        self.assertEqual(crossing['validDays'],2)
        self.assertEqual(crossing['avgStarts'],1)
