# 지도 이동 참조

`district-bounds.js`는 southkorea/seoul-maps의 통계청(KOSTAT) 2013 서울 자치구 단순화 경계 좌표에서 최소/최대 경도·위도만 추출한 지도 카메라 이동용 참조입니다.

출처: https://github.com/southkorea/seoul-maps/blob/master/kostat/2013/json/seoul_municipalities_geo_simple.json

최근 행정경계로 검증하지 않은 옛 자료이므로 **현행 자치구 경계선을 그리거나 충전소의 행정구역을 판정하는 데 사용하지 않습니다.** 필터는 실제 API 주소의 자치구를 사용합니다. 충전소 위치는 API lat/lng만 사용하며 없는 좌표를 이 참조로 채우지 않습니다. 현행 경계 자료를 확보하기 전 경계 강조는 보류합니다.
