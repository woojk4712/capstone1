| Endpoint | HTTP | status | count | reason | items 길이 | 오류 |
|---|---:|---|---:|---|---:|---|
| /api/system/status | 200 | — | — | — | — | — |
| /api/chargers | 200 | — | 0 | — | 0 | — |
| /api/analysis/stations | 200 | — | 100 | — | 100 | — |
| /api/analysis/overview?radius=500 | 200 | ok | 100 | — | 100 | — |
| /api/analysis/recovery-ranking | 200 | ok | 0 | no_current_stopped_core_chargers | 0 | — |
| /api/analysis/potential-impact | 200 | ok | 231 | — | 231 | — |
| /api/operations/stations?stopped_only=true | 200 | ok | 24 | — | 24 | — |
| /api/analysis/maintenance/SE000001 | 200 | READY | — | — | — | — |

—는 해당 필드가 없다는 의미이며 0건과 다릅니다.
충전기 API의 eligible items와 원자료 unclassified_items 건수는 JSON에서 구분합니다.
정비 API의 데이터는 items 대신 heatmap / oneHour / twoHour에 있습니다.