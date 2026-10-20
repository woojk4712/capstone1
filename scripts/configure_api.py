"""Read-only presence check. Keys and URLs are never copied from templates."""
import json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.app.settings import Settings,read_env

def configure(root=ROOT):
    return Settings(read_env(Path(root)/'.env')).presence()

if __name__=='__main__':
    print(json.dumps(configure()))
