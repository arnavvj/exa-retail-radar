import hashlib
import json
import time
from pathlib import Path

ROOT = Path(__file__).parent / "cache"


def _path(op, key):
    digest = hashlib.sha1(json.dumps(key, sort_keys=True).encode()).hexdigest()[:16]
    return ROOT / op / f"{digest}.json"


def get(op, key, max_age=None):
    p = _path(op, key)
    if not p.exists() or (max_age and time.time() - p.stat().st_mtime > max_age):
        return None
    return json.loads(p.read_text())


def put(op, key, value):
    p = _path(op, key)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, indent=2, default=str))
