"""Physical-address evidence for official registry matching; never name similarity approval."""
import re
import unicodedata
from functools import lru_cache
from .analysis import normalize_name


@lru_cache(maxsize=65536)
def physical_address(value):
    value=unicodedata.normalize('NFKC',str(value or ''))
    value=re.sub(r'^\s*서울(?:특별시|시)?(?=\s)','서울특별시',value)
    value=re.sub(r'\([^)]*\)',' ',value)
    value=' '.join(value.split())
    prefix=re.match(r'^(서울특별시)\s+(\S+구)\s+(.+)',value)
    if not prefix:return None
    city,district,tail=prefix.groups()
    # Keep underground and mountain parcel distinctions; never equate road and parcel addresses.
    road=re.match(r'([가-힣A-Za-z·]+(?:\d+[가-힣A-Za-z·]*)?(?:로|길)(?:\s*\d+[가-힣A-Za-z·]*(?:길|로))?)\s*(지하)?\s*(\d+(?:-\d+)?)(?=\D|$)',tail)
    if road:
        street,underground,building=road.groups()
        return {'kind':'road','district':district,'street':normalize_name(street),
                'number':building,'underground':bool(underground),
                'key':normalize_name(city+district+street+(underground or '')+building)}
    parcel=re.match(r'([가-힣0-9·]+(?:동|가))\s*(산)?\s*(\d+(?:-\d+)?)(?=\D|$)',tail)
    if parcel:
        dong,mountain,lot=parcel.groups()
        return {'kind':'parcel','district':district,'street':normalize_name(dong),
                'number':lot,'mountain':bool(mountain),
                'key':normalize_name(city+district+dong+(mountain or '')+lot)}
    return None


def address_key(value):
    parsed=physical_address(value)
    if parsed:return parsed['key']
    value=re.sub(r'\([^)]*\)','',str(value or '')).replace('서울시','서울특별시')
    return normalize_name(value)


def station_address_index(stations):
    result={}
    for station in stations:
        address=physical_address(station.get('addr'))
        if address:result.setdefault(address['key'],[]).append(station)
    return result


def bridge_candidates(facility,stations,address_index=None):
    address=physical_address(facility['address'])
    if not address:return [],'address_not_structured'
    if facility.get('district') and facility['district']!=address['district']:
        return [],'registry_district_conflict'
    same_address=(address_index if address_index is not None else station_address_index(stations)).get(address['key'],[])
    exact=[s for s in same_address if normalize_name(s.get('statNm'))==facility['normalized_name']]
    if len(exact)==1:return exact,'exact_registry_name_and_physical_address'
    if len(exact)>1:return exact,'multiple_d3_stat_ids_same_name_address'
    # Independent address proof may bridge a different D3 label, but never choose among co-located IDs.
    if len(same_address)==1:return same_address,'unique_registry_physical_address'
    return same_address,'multiple_d3_stat_ids_at_address' if same_address else 'no_d3_physical_address_match'
