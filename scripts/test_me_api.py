"""Run from the user's Windows terminal. Never invoke automatically in agent QA."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

if __name__=='__main__':
    from backend.app.local_tests import test_me
    sys.exit(test_me())
