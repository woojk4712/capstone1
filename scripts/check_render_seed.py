"""Build-time seed check, independent of API connectivity and runtime DBs."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.deployment_seed import check_seed

if __name__ == '__main__':
    manifest = check_seed()
    print('Render seed verified:', manifest['counts'])
