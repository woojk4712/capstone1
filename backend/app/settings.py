"""External credentials are read exclusively from the project root .env."""
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = ROOT / '.env'
NAMES = ('ME_SERVICE_KEY', 'ME_URL', 'ME_STATUS_URL', 'KEPCO_SERVICE_KEY', 'KEPCO_URL')

def clean_credential(value):
    return ''.join(c for c in value if not c.isspace() and unicodedata.category(c) != 'Cf')

def read_env(path=None):
    path = Path(path).resolve() if path is not None else ENV_PATH
    values = {}
    if not path.exists():
        return values
    raw = path.read_bytes()
    text = raw.decode('utf-16' if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig')
    text = ''.join(c for c in text if unicodedata.category(c) != 'Cf')
    # dotenv is optional for dependency-free verification, and required locally.
    # No interpolation from ambient process variables is permitted.
    try:
        from dotenv import dotenv_values
        from io import StringIO
        parsed = dotenv_values(stream=StringIO(text), interpolate=False)
        return {k: clean_credential(v or '') if k in NAMES else v or '' for k, v in parsed.items()}
    except ImportError:
        pass
    for line in text.splitlines():
        match = re.match(r'^\s*(?:export\s+)?([A-Za-z_][A-Za-z_0-9]*)\s*=\s*(.*)$', line)
        if not match:
            continue
        key, value = match.groups()
        if value.startswith(('"', "'")):
            quote = value[0]
            end = value.find(quote, 1)
            value = value[1:end] if end >= 1 else value[1:]
        else:
            value = re.split(r'\s+#', value, maxsplit=1)[0].strip()
        values[key] = clean_credential(value) if key in NAMES else value
    return values

@dataclass(repr=False)
class Settings:
    values: dict = field(repr=False)
    me_contract: dict = field(default_factory=dict, repr=False)

    @classmethod
    def load(cls):
        from .services.me_classification import load_contract
        return cls(read_env(), me_contract=load_contract(ROOT))

    def get(self, name, default=''):
        return self.values.get(name, default)

    def presence(self):
        return {name: bool(self.get(name)) for name in NAMES}

    def redact(self, text):
        from urllib.parse import quote, unquote
        for name in NAMES:
            value = self.get(name)
            if value:
                for variant in (value, unquote(value), quote(value, safe='')):
                    if variant:
                        text = text.replace(variant, '[REDACTED]')
        return text

    def scrub(self, value):
        if isinstance(value, str): return self.redact(value)
        if isinstance(value, list): return [self.scrub(v) for v in value]
        if isinstance(value, dict): return {self.redact(str(k)):self.scrub(v) for k,v in value.items()}
        return value
