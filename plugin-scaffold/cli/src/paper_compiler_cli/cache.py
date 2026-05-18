from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Optional

from .config import Config, cache_root

PARSER_VERSION = "5"


def _safe_id(paper_id: str) -> str:
    return paper_id.replace(":", "_").replace("/", "_")


def s2_cache_path(cfg: Config, key: str) -> Path:
    h = hashlib.sha1(key.encode()).hexdigest()
    p = cache_root(cfg) / "s2" / h[:2] / f"{h}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def s2_cache_get(cfg: Config, key: str, ttl_days: Optional[int] = None) -> Optional[Any]:
    p = s2_cache_path(cfg, key)
    if not p.exists():
        return None
    if ttl_days is not None:
        age_days = (time.time() - p.stat().st_mtime) / 86400.0
        if age_days > ttl_days:
            return None
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError:
        return None


def s2_cache_put(cfg: Config, key: str, value: Any) -> None:
    p = s2_cache_path(cfg, key)
    p.write_text(json.dumps(value))


def paper_source_dir(cfg: Config, paper_id: str) -> Path:
    p = cache_root(cfg) / "papers" / _safe_id(paper_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


def parsed_ir_path(cfg: Config, paper_id: str) -> Path:
    p = cache_root(cfg) / "parsed" / f"{_safe_id(paper_id)}.v{PARSER_VERSION}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p
