from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

if sys.version_info >= (3, 11):
    import tomllib as toml_lib
else:
    import tomli as toml_lib  # type: ignore[no-redef]


@dataclass
class S2Config:
    api_key: Optional[str] = None
    rate_limit_rps: float = 1.0


@dataclass
class CompileConfig:
    max_depth: int = 2
    max_papers: int = 200
    max_s2_requests: int = 500
    max_wall_seconds: int = 1200
    classifier_llm_max_calls: int = 50
    atom_llm_max_calls: int = 80
    expand_top_k: int = 20
    atom_paper_count: int = 10


@dataclass
class ParserConfig:
    prefer: str = "tex"
    pdf_backend: str = "marker"


@dataclass
class OutputConfig:
    research_dir: str = "research"
    research_md_max_tokens: int = 8000


@dataclass
class CacheConfig:
    dir: str = "~/.cache/paper-compiler"
    ttl_metadata_days: int = 30


@dataclass
class LLMConfig:
    provider: str = "anthropic"
    classifier_model: str = "claude-haiku-4-5"
    atom_model: str = "claude-haiku-4-5"
    api_key: Optional[str] = None


@dataclass
class Config:
    s2: S2Config = field(default_factory=S2Config)
    compile: CompileConfig = field(default_factory=CompileConfig)
    parser: ParserConfig = field(default_factory=ParserConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)


_SEARCH_PATHS = [
    Path("paper-compiler.toml"),
    Path.home() / ".config" / "paper-compiler" / "config.toml",
]


def _merge(section: object, data: dict) -> None:
    for k, v in data.items():
        if hasattr(section, k):
            setattr(section, k, v)


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip("'\"")
            if key and key not in os.environ:
                os.environ[key] = val
    except OSError:
        return


def load_config(explicit_path: Optional[Path] = None) -> Config:
    # Pick up .env from cwd before reading env vars, so SEMANTIC_SCHOLAR_API_KEY
    # / ANTHROPIC_API_KEY survive across shells without sourcing manually.
    _load_dotenv(Path(".env"))
    _load_dotenv(Path("paper-compiler.env"))

    cfg = Config()
    paths = [explicit_path] if explicit_path else _SEARCH_PATHS
    for p in paths:
        if p is None or not p.exists():
            continue
        with open(p, "rb") as fh:
            raw = toml_lib.load(fh)
        for key in ("s2", "compile", "parser", "output", "cache", "llm"):
            if key in raw and isinstance(raw[key], dict):
                _merge(getattr(cfg, key), raw[key])
        break

    cfg.s2.api_key = cfg.s2.api_key or os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
    cfg.llm.api_key = cfg.llm.api_key or os.environ.get("ANTHROPIC_API_KEY")
    return cfg


def apply_overrides(cfg: Config, **overrides) -> Config:
    """Apply CLI-flag overrides onto nested config sections."""
    for k, v in overrides.items():
        if v is None:
            continue
        target_section, _, attr = k.partition(".")
        section = getattr(cfg, target_section, None)
        if section is not None and hasattr(section, attr):
            setattr(section, attr, v)
    return cfg


def cache_root(cfg: Config) -> Path:
    p = Path(os.path.expanduser(cfg.cache.dir))
    p.mkdir(parents=True, exist_ok=True)
    return p
