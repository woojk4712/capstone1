"""Read-only view of collected ME observations, independent of research matching.

No HTTP collection and no database writes. Old observations remain explicitly old.
"""
from collections import defaultdict
import json
import threading
from datetime import datetime, timezone
from .services.me_api import model, classifications


class OperationalView:
    def __init__(self, external):
        self.external = external
        self._observations = {}
        self._observation_lock = threading.RLock()

    def inventory(self, observation_at=None):
        e = self.external
        with self._observation_lock:
            # Both reads belong to one SQLite read transaction, including during collection commits.
            with e.storage.connection() as db:
                db.execute('BEGIN')
                state_row=db.execute("SELECT body FROM provider_state WHERE provider='ME'").fetchone()
                state=json.loads(state_row[0]) if state_row else {}
                current=state.get('last_success_at')
                target=observation_at or current
                cached=self._observations.get(target)
                if cached is None:
                    if target!=current:raise ObservationChanged('observation_changed')
                    raw=db.execute('SELECT body,collected_at FROM current_chargers ORDER BY stat_id,charger_id').fetchall()
                else:raw=None
            if cached is None:
                rows=[model(json.loads(body),e.settings,stamp,True) for body,stamp in raw]
                if any(c['collected_at']!=target for c in rows):raise ObservationChanged('observation_changed')
                cached={'items':rows,'inventory_count':len(rows),'total':len(rows),'last_success_at':target,
                        'observationAt':target,'revision':'ME:'+str(target),'observation_only':True}
                self._observations[target]=cached
                while len(self._observations)>2:self._observations.pop(next(iter(self._observations)))
        types, states = classifications(e.settings)
        try:age=(datetime.now(timezone.utc)-datetime.fromisoformat(target)).total_seconds()
        except (ValueError,TypeError):age=float('inf')
        fresh=e.is_fresh() and 0<=age<=900
        return {**cached,'stale':not fresh,'superseded':current!=target,
                'classification_verified': bool(types and states),
                'statusClassificationVerified': bool(states),
                'chargerTypeClassificationVerified': bool(types)}

    def stations(self, observation_at=None):
        data = self.inventory(observation_at)
        groups = defaultdict(list)
        for c in data['items']:
            if (str(c.get('addr', '')).strip().startswith('서울특별시')
                    and c.get('delYn') != 'Y' and c['latitude'] is not None
                    and c['longitude'] is not None):
                groups[str(c['statId'])].append(c)
        items = []
        for sid, cs in groups.items():
            first = cs[0]
            items.append({'analysisStationId': 'ME:' + sid, 'statId': sid,
                          'statNm': first.get('statNm'), 'addr': first.get('addr'),
                          'lat': first['latitude'], 'lng': first['longitude'], 'chargers': cs})
        return {k: v for k, v in data.items() if k != 'items'} | {
            'items': items, 'total': len(items),
            'chargerCount': sum(len(s['chargers']) for s in items)}

    def simulate(self, ids, station_ids, replay=False, observation_at=None):
        data = self.stations(observation_at)
        if data['stale'] and not replay:
            raise ValueError('최신 관측 필요: 과거 관측 재현을 명시적으로 선택하세요')
        if not data['statusClassificationVerified']:
            raise ValueError('환경공단 상태 코드 검증 필요')
        scope = set(station_ids)
        if not scope <= {s['statId'] for s in data['items']}:
            raise ValueError('서울 관측 시설만 선택할 수 있습니다')
        cs = [(s['analysisStationId'] + ':' + str(c['chgerId']), c)
              for s in data['items'] if s['statId'] in scope for c in s['chargers']]
        lookup = {key: c for key, c in cs}
        selected = set(ids)
        if not selected <= lookup.keys() or any(
            lookup[i]['status'] != 'STOPPED' or lookup[i]['output_kw'] is None
            or lookup[i]['output_kw'] <= 0 for i in selected
        ):
            raise ValueError('출력이 확인된 운영중지 설비만 선택할 수 있습니다')
        def power(statuses):
            units = [c for _, c in cs if c['status'] in statuses]
            return None if any(c['output_kw'] is None for c in units) else sum(c['output_kw'] for c in units)
        before = {'normalKw': power(('AVAILABLE', 'CHARGING')), 'stoppedKw': power(('STOPPED',)),
                  'maintenanceKw': power(('MAINTENANCE',)),
                  'stoppedCount': sum(c['status'] == 'STOPPED' for _, c in cs)}
        delta = sum(lookup[i]['output_kw'] for i in selected)
        after = dict(before, normalKw=None if before['normalKw'] is None else before['normalKw'] + delta,
                     stoppedKw=None if before['stoppedKw'] is None else before['stoppedKw'] - delta,
                     stoppedCount=before['stoppedCount'] - len(selected))
        return {'before': before, 'after': after, 'recoveredKw': delta,
                'recoveryRate': delta / before['normalKw'] * 100 if before['normalKw'] else None,
                'selectedIds': sorted(selected), 'stationIds': sorted(scope),
                'observationAt': data['last_success_at'], 'stale': data['stale'], 'replay': replay,
                'revision':data['revision'],
                'warning': '환경공단 운영현황 기반 단순 시나리오 · D1 이용수요 미연결 · 영향도 순위 제외'}


class ObservationChanged(ValueError):
    pass
