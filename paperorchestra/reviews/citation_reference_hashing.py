from __future__ import annotations

import hashlib


def _hash_identity(prefix: str, value: str) -> str:
    return f"{prefix}:{hashlib.sha256(value.encode('utf-8')).hexdigest()[:12]}"
