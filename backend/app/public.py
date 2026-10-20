"""Public server: read APIs and same-origin, non-persistent simulations only."""
from .main import create_app
import os

app = create_app(public=True, public_origin=os.environ.get('PUBLIC_ORIGIN', '').rstrip('/') or None)
