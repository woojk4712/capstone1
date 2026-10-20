"""Record provenance when intentionally replacing public source datasets."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = [
    ('서울시 소유 전기차 충전소의 충전량(12월말까지).xlsx', 'D1', 'OA-22249', 'F'),
    ('서울시 소유 전기차충전기 일별 시간별 충전현황(2025년).xlsx', 'D2', 'OA-22258', 'F'),
    ('서울시 소유 전기차 충전소 정보.csv', 'OA-21712', 'OA-21712', 'S'),
]

if __name__ == '__main__':
    files = []
    for filename, code, dataset, kind in SOURCES:
        path = ROOT / filename
        files.append(dict(code=code, path=filename, bytes=path.stat().st_size,
                          sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                          source=f'https://data.seoul.go.kr/dataList/{dataset}/{kind}/1/datasetView.do',
                          publisher='서울특별시', license='공공누리 제1유형 (출처표시)'))
    (ROOT / 'data/input/manifest.json').write_text(json.dumps(
        {'recorded_at': '2026-10-20', 'files': files}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
