"""Isolated D1-D3 scope tests; no real API calls, no production approvals."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from backend.app.analysis import AnalysisService,HEADERS
from backend.app.core import ExternalService
from backend.app.storage import Storage,now
from backend.app.settings import Settings

class AnalysisDatasetTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.folder=Path(self.tmp.name);self.source=self.folder/'fixture.xlsx';self.source.write_bytes(b'TEST SOURCE ONLY')
        self.external=ExternalService(Settings({}),Storage(self.folder/'external.sqlite'))
        self.service=AnalysisService(self.external,self.folder/'analysis.sqlite')
        self.raw=[(4,HEADERS),(5,['2025-01-01','Fixture A','급속','10']),
                  (6,['2025-01-01','Fixture A','급속','10']),(7,['2025-02-01','Fixture A','급속','0']),
                  (8,['2025-01-01','Fixture B','완속','20']),(9,['2024-01-01','Fixture C','급속','30'])]
        self.prepare()
        self.external.storage.save_me([self.row('A'),self.row('B',lat='37.501',addr='경기도 경계 테스트'),
                                      self.row('DELETED',delYn='Y')],now(),200)

    def row(self,sid,**kwargs):
        return dict({'statId':sid,'chgerId':'1','statNm':'Fixture '+sid,'addr':'서울특별시 강남구 테스트',
                     'lat':'37.5','lng':'127','output':'100','chgerType':'FIXTURE_FAST','stat':'ready','delYn':'N','limitYn':'N'},**kwargs)

    def prepare(self):
        with patch('backend.app.analysis.xlsx_rows',return_value=iter(self.raw)):
            return self.service.prepare_d1(self.source)

    def confirm(self):self.service.confirm('Fixture A','A','address registry independently checked for fixture only')

    def test_d1_2025_fast_aggregation_preserves_duplicates_zero_and_original(self):
        meta=self.service.meta('d1');self.assertEqual(meta['rows'],5);self.assertEqual(meta['fast_station_names'],1)
        self.assertEqual(meta['zero_rows'],1);self.assertEqual(meta['duplicate_excess_rows'],1)
        with self.service.db() as db:row=db.execute('SELECT annual_fast_kwh,monthly_fast_kwh,fast_row_count FROM d1_demand').fetchone()
        self.assertEqual(row[0],20);self.assertEqual(json.loads(row[1])[:3],[20,0,None]);self.assertEqual(row[2],3)
        self.assertEqual(self.source.read_bytes(),b'TEST SOURCE ONLY')
        self.assertIn('normalized_station_name',(self.folder/'analysis/d1-preprocessed.csv').read_text(encoding='utf-8-sig'))

    def test_exact_name_candidate_never_auto_confirms(self):
        with patch.object(self.service,'prepare_d1',return_value=self.service.meta('d1')):
            counts=self.service.prepare_matches()
        self.assertEqual(counts['confirmed'],0);self.assertEqual(counts['review'],1)
        self.assertEqual(self.service.stations()['total'],0)
        self.assertTrue(any(r['match_confidence']==1 for r in self.service.match_rows()))

    def test_confirmed_core_exists_independently_of_classification(self):
        self.confirm();result=self.service.stations()
        self.assertEqual(result['total'],1);self.assertTrue(result['analysisDatasetReady'])
        self.assertFalse(result['classificationVerified']);station=result['items'][0]
        self.assertEqual(station['annualFastKwh2025'],20)
        self.assertIsNone(station['chargerCount']);self.assertIsNone(station['totalRatedOutputKw'])
        self.assertEqual(self.service.alternatives('A')['message'],'분류 검증 필요')

    def test_alternative_crosses_boundary_excludes_same_id_and_deleted(self):
        self.external.settings=Settings({'ME_MAPPING_VERIFIED':'true','ME_FAST_TYPES':'["FIXTURE_FAST"]','ME_STATUS_MAP':'{"ready":"AVAILABLE"}'})
        self.confirm();result=self.service.alternatives('A',500)
        self.assertEqual([row['statId'] for row in result['items']],['B'])
        self.assertEqual(result['totalRatedOutputKw'],100)
        snapshot=self.service.legacy_snapshot()
        self.assertEqual(len([s for s in snapshot['stations'] if s['analysis_target']]),1)
        self.assertEqual(len([s for s in snapshot['stations'] if not s['analysis_target']]),1)
        from services.engine import analyze
        result=analyze(snapshot)
        self.assertEqual(len(result['stations']),1);self.assertEqual(result['stations'][0]['alternative_kw'],100)

    def test_core_requires_active_valid_equipment(self):
        self.confirm();self.external.storage.save_me([self.row('A',delYn='Y')],now(),200)
        self.assertEqual(self.service.stations()['total'],0)

    def test_name_only_confirmation_is_rejected_and_unique_facility_is_enforced(self):
        with self.assertRaises(ValueError):self.service.confirm('Fixture A','A','same normalized name only')
        self.confirm()
        with self.service.db() as db:
            db.execute('INSERT INTO d1_demand VALUES (?,?,?,?,?)',('Alias A','aliasa',50,'[]',1))
        with self.assertRaises(sqlite3.IntegrityError):
            self.service.confirm('Alias A','A','address registry checked for fixture alias')
        self.assertEqual(self.service.match_summary()['confirmed'],1)

    def test_integrated_fastapi_analysis_routes_do_not_collide_with_html_page(self):
        from fastapi.testclient import TestClient
        from backend.app.main import create_app
        self.confirm()
        with TestClient(create_app(self.external,collect=False)) as client:
            result=client.get('/api/analysis/stations')
            self.assertEqual(result.status_code,200);self.assertEqual(result.json()['total'],1)
            self.assertEqual(client.get('/api/analysis/matches').status_code,200)
            self.assertEqual(client.get('/analysis').status_code,200)

if __name__=='__main__':unittest.main()
