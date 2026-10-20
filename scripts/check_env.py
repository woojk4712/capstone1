import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
if __name__=='__main__':
    from backend.app.local_tests import check_environment
    sys.exit(check_environment())
