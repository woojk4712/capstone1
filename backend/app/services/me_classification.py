"""Reviewed ME v1.25 appendix codes, independent of KEPCO and credentials."""
import hashlib
import json
from pathlib import Path

STATUS_LABELS = {'0':'알수없음','1':'통신이상','2':'충전대기 / 사용가능',
                 '3':'충전중','4':'운영중지 · 복구 검토','5':'점검중','6':'예약중','9':'상태미확인'}
TYPE_LABELS = {'01':'DC차데모','02':'AC완속','03':'DC차데모+AC3상','04':'DC콤보',
               '05':'DC차데모+DC콤보','06':'DC차데모+AC3상+DC콤보','07':'AC3상',
               '08':'DC콤보(완속)','09':'NACS','10':'DC콤보+NACS','11':'DC콤보2(버스전용)'}

def load_contract(root):
    """Only activate reviewed mapping while its original official source matches."""
    try:
        contract=json.loads((Path(root)/'docs/me_v125_classification.json').read_text(encoding='utf-8'))
        source=Path(root)/'docs'/Path(contract['source_file']).name
        if hashlib.sha256(source.read_bytes()).hexdigest()!=contract['source_sha256']:
            return {}
        return contract
    except (OSError,ValueError,KeyError,TypeError):
        return {}
