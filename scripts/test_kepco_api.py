"""Run locally after reviewing docs/kepco_request_contract.json."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

if __name__=='__main__':
    from backend.app.local_tests import test_kepco
    sys.exit(test_kepco())
