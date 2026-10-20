import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
from backend.app.settings import runtime_directory
DATA = runtime_directory()
DATA.mkdir(parents=True, exist_ok=True)

def load_env():
    from backend.app.settings import read_env, NAMES, Settings
    values = Settings.load().values if os.environ.get('CHARGEOPS_DEPLOYMENT') == 'render' else read_env()
    for name, value in values.items():
        if name in NAMES:
            os.environ[name] = value
        else:
            os.environ.setdefault(name, value)
    for name in NAMES:
        if name not in values:
            os.environ.pop(name, None)

load_env()
