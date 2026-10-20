"""Synthetic fixtures, explicitly selected by the user. Never a live fallback."""
from datetime import datetime,timedelta
from .store import now

def sample_snapshot():
    stamp=now()
    names=[('종로구','광화문 공영주차장',37.572,126.977),('종로구','경복궁 주차장',37.579,126.978),('중구','서울시청 서소문청사',37.564,126.974),('중구','남산 공영주차장',37.552,126.987),('용산구','용산구청',37.532,126.990),('성동구','서울숲 주차장',37.545,127.043),('강남구','삼성동 공영주차장',37.514,127.061),('강남구','강남구청',37.517,127.047),('서초구','반포한강공원',37.510,126.997),('마포구','월드컵공원',37.568,126.897),('영등포구','여의도한강공원',37.528,126.934),('송파구','잠실종합운동장',37.514,127.073),('성북구','성북구청',37.589,127.017),('동대문구','청량리 공영주차장',37.579,127.044),('광진구','광진구청',37.538,127.082),('강서구','강서구청',37.551,126.850),('노원구','노원구청',37.654,127.056),('은평구','은평구청',37.603,126.929),('동작구','동작구청',37.513,126.940),('금천구','금천구청',37.457,126.895),('강동구','강동구청',37.530,127.124),('관악구','관악구청',37.478,126.951),('도봉구','도봉구청',37.669,127.047),('양천구','양천구청',37.517,126.866)]
    stations=[]
    for i,(district,name,lat,lon) in enumerate(names):
        cs=[]
        for j in range(3+(i%3)):
            status='STOPPED' if (i+j)%4==0 else 'COMM_ERROR' if (i+j)%11==0 else 'CHARGING' if j%2 else 'AVAILABLE'
            c=dict(id=f'SAMPLE-{i+1:03}-{j+1:02}',status=status,power_kw=[50,100,200][(i+j)%3],physical_verified=True,sharing_verified=True,fast_verified=True,access_verified=True,compatible_verified=True,last_verified_at=stamp,ttl_minutes=1000000,source_updated_at=stamp,source_status_raw='synthetic')
            if i==3 and j==1: c.update(status='STOPPED',sharing_verified=False)
            cs.append(c)
        annual=105000+i*13841
        weights=[.7+((m+i)%5)*.15 for m in range(12)]; monthly=[annual*w/sum(weights) for w in weights]
        stations.append(dict(id=f'SAMPLE-{i+1:03}',name=name,district=district,address=f'서울특별시 {district} · 예시 위치',lat=lat,lon=lon,match_status='approved' if i!=17 else 'review_required',annual_kwh=annual,monthly_kwh=monthly,chargers=cs,quality_flags=[],fast_only_history_verified=False,covered_days=None))
    return dict(id='sample-2025-v1',observed_at=stamp,stations=stations,network_complete=True,quality_flags=['샘플 데이터 · 실제 관측 결과 아님'],mode='sample',mapping_version='sample-v1')
