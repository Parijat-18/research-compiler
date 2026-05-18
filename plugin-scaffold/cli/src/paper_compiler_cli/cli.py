from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from .config import load_config
from .resolve import Candidate, resolve


def _candidates_to_json(cs: list[Candidate]) -> list[dict[str, Any]]:
    return [
        {
            "paper_id": c.paper_id,
            "title": c.title,
            "year": c.year,
            "authors": c.authors,
            "external_ids": c.external_ids.model_dump(exclude_none=True),
            "confidence": c.confidence,
        }
        for c in cs
    ]


def cmd_resolve(args: argparse.Namespace) -> int:
    cfg = load_config(Path(args.config) if args.config else None)
    candidates = asyncio.run(resolve(cfg, args.input))
    if not candidates:
        json.dump({"input": args.input, "candidates": [], "error": "no match"}, sys.stdout, indent=2)
        return 1
    json.dump({"input": args.input, "candidates": _candidates_to_json(candidates)}, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    from .compile import build_paper
    from .config import apply_overrides

    cfg = load_config(Path(args.config) if args.config else None)
    apply_overrides(
        cfg,
        **{
            "compile.max_depth": args.max_depth,
            "compile.max_papers": args.max_papers,
            "compile.expand_top_k": args.top_k,
            "compile.max_s2_requests": args.max_s2_requests,
            "compile.max_wall_seconds": args.max_wall_seconds,
            "compile.classifier_llm_max_calls": 0 if args.no_llm else args.classifier_llm_calls,
            "compile.atom_llm_max_calls": 0 if args.no_llm else args.atom_llm_calls,
            "compile.atom_paper_count": args.atom_papers,
            "output.research_md_max_tokens": args.research_md_tokens,
        },
    )
    return asyncio.run(build_paper(cfg, args.paper_id, Path(args.out), refresh=args.refresh))


def cmd_parse(args: argparse.Namespace) -> int:
    from .compile import parse_only

    cfg = load_config(Path(args.config) if args.config else None)
    return asyncio.run(parse_only(cfg, args.input, Path(args.out)))


def cmd_ingest(args: argparse.Namespace) -> int:
    from .ingest import ingest_paper_into_research

    cfg = load_config(Path(args.config) if args.config else None)
    return asyncio.run(
        ingest_paper_into_research(cfg, args.input, Path(args.research_dir), force=args.force)
    )


def cmd_cache(args: argparse.Namespace) -> int:
    print(json.dumps({"action": args.action, "note": "not implemented in v0.1"}))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="paper-compiler")
    parser.add_argument("--config", help="Path to paper-compiler.toml")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_resolve = sub.add_parser("resolve", help="Resolve input to canonical paper ID.")
    p_resolve.add_argument("input")
    p_resolve.set_defaults(func=cmd_resolve)

    p_parse = sub.add_parser("parse", help="Resolve, acquire, and parse a single paper to IR JSON.")
    p_parse.add_argument("input")
    p_parse.add_argument("--out", required=True)
    p_parse.set_defaults(func=cmd_parse)

    p_build = sub.add_parser("build", help="Compile paper + neighborhood into research/.")
    p_build.add_argument("paper_id")
    p_build.add_argument("--out", default="research")
    p_build.add_argument("--refresh", action="store_true")
    p_build.add_argument("--max-depth", type=int, default=None, help="Max citation graph depth (default from config, usually 2).")
    p_build.add_argument("--max-papers", type=int, default=None, help="Max papers in neighborhood (default 200).")
    p_build.add_argument("--top-k", type=int, default=None, dest="top_k", help="How many depth-1 papers to expand to depth-2.")
    p_build.add_argument("--max-s2-requests", type=int, default=None, help="Hard cap on Semantic Scholar API calls.")
    p_build.add_argument("--max-wall-seconds", type=int, default=None, help="Wall-clock budget for the compile.")
    p_build.add_argument("--classifier-llm-calls", type=int, default=None, help="Max LLM calls for citation edge classifier.")
    p_build.add_argument("--atom-llm-calls", type=int, default=None, help="Max LLM calls for atom extraction (shared across target + cited papers).")
    p_build.add_argument("--atom-papers", type=int, default=None, help="How many top-ranked cited papers to extract atoms from in addition to the target (default 10).")
    p_build.add_argument("--no-llm", action="store_true", help="Disable LLM passes entirely; heuristics only.")
    p_build.add_argument("--research-md-tokens", type=int, default=None, help="Hard token budget for research.md (default 8000).")
    p_build.set_defaults(func=cmd_build)

    p_ingest = sub.add_parser("ingest", help="Add one more paper to an existing research/ corpus.")
    p_ingest.add_argument("input", help="arxiv id / DOI / s2 id / URL / local path")
    p_ingest.add_argument("--research-dir", default="research")
    p_ingest.add_argument("--force", action="store_true", help="Re-ingest even if paper already in DB.")
    p_ingest.set_defaults(func=cmd_ingest)

    p_cache = sub.add_parser("cache", help="Cache management.")
    p_cache.add_argument("action", choices=["prune", "info"])
    p_cache.add_argument("--older-than", default="90d")
    p_cache.set_defaults(func=cmd_cache)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
