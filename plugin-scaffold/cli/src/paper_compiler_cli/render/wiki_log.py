"""Append-only `research/wiki/log.md` writer.

Karpathy's llm-wiki uses a chronological event log to make it obvious *when*
the knowledge base last changed and *what kind* of change it was. We record
every compile, ingest, query (when promoted), and lint pass.

Format: a top-level H2 header per entry with a timestamp + event type, then
short bullet body. Append-only.
"""

from __future__ import annotations

import time
from pathlib import Path


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime())


def append_log(wiki_dir: Path, event: str, body_lines: list[str]) -> None:
    wiki_dir.mkdir(parents=True, exist_ok=True)
    log_path = wiki_dir / "log.md"
    header_already = log_path.exists() and log_path.read_text().startswith("# Wiki log")
    block = [f"\n## {_now_iso()} — {event}"]
    for line in body_lines:
        block.append(f"- {line}")
    block.append("")
    with open(log_path, "a", encoding="utf-8") as fh:
        if not header_already:
            fh.write("# Wiki log\n\nAppend-only record of compile / ingest / query / lint events.\n")
        fh.write("\n".join(block))


def log_compile(wiki_dir: Path, target_paper_id: str, stats: dict) -> None:
    append_log(
        wiki_dir,
        "compile",
        [
            f"target: `{target_paper_id}`",
            f"papers in neighborhood: {stats.get('papers_in_neighborhood', 0)} ({stats.get('papers_acquired', 0)} acquired)",
            f"atoms: {stats.get('atoms_extracted', 0)}",
            f"communities: {stats.get('communities', 0)}",
            f"wall: {stats.get('wall_time_seconds', 0)}s",
            f"llm backend: {stats.get('llm_backend', 'none')}",
        ],
    )
