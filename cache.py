import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).parent / "cache"


def _path(op, key):
    digest = hashlib.sha1(json.dumps(key, sort_keys=True).encode()).hexdigest()[:16]
    return ROOT / op / f"{digest}.json"


def get(op, key):
    p = _path(op, key)
    return json.loads(p.read_text()) if p.exists() else None


def put(op, key, value):
    p = _path(op, key)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, indent=2, default=str))
