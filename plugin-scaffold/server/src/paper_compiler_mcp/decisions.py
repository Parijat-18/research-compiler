"""Parse and append entries in ``research/decisions.md``.

The file is append-only structured markdown. Each entry is an H2 with an
ISO timestamp + slug, followed by bullet lines of ``**Key:** value``.
Format:

    ## 2026-05-19T14:32Z · loss-form
    **Category:** objective
    **Atom:** atom_uid abc123def456
    **Decision:** Use MSE rather than contrastive InfoNCE.
    **Why:** Paper's section 4.2 lists both; ablation A.3 confirms MSE.
    **Source:** chunk_id=147, paper_id=s2:530dab...

Round-trippable: grep-friendly, git-diff-friendly, machine-parseable.
"""

from __future__ import annotations

import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

# H2 header: "## <ISO-Z timestamp> · <slug>"
_HEADER_RE = re.compile(
    r"^##\s+(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?Z)\s+·\s+(\S+)\s*$"
)
# Bullet: "**Key:** value" (loose — allows colon or no colon, trims spaces)
_BULLET_RE = re.compile(r"^\*\*([A-Za-z][A-Za-z _-]*):\*\*\s*(.*)$")


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime())


def _slugify(s: str, max_len: int = 40) -> str:
    """Turn an arbitrary string into a filesystem/slug-safe token.

    Keeps lowercase alphanumeric + hyphen; collapses everything else to a
    single hyphen. Truncates to ``max_len`` and strips trailing hyphens.
    """
    s = (s or "").lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    if len(s) > max_len:
        s = s[:max_len].rstrip("-")
    return s or "decision"


def parse_file(path: Path) -> list[dict]:
    """Parse a ``decisions.md`` file into a list of entry dicts.

    Returns entries in file order (oldest first). Each dict carries:

      - ``timestamp``: the H2 timestamp string (ISO-Z).
      - ``slug``: the H2 slug.
      - ``body``: dict of {key_lowercase: value} from the **Key:** bullets.
      - ``raw``: the verbatim block (header + bullets), useful for echoing back.

    Robust: malformed entries are skipped silently. Files that don't exist
    return an empty list.
    """
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []

    entries: list[dict] = []
    current_header: Optional[tuple[str, str]] = None
    current_body: dict[str, str] = {}
    current_raw: list[str] = []

    def _flush() -> None:
        if current_header is None:
            return
        ts, slug = current_header
        entries.append({
            "timestamp": ts,
            "slug": slug,
            "body": dict(current_body),
            "raw": "\n".join(current_raw).rstrip(),
        })

    for line in text.splitlines():
        m = _HEADER_RE.match(line)
        if m:
            _flush()
            current_header = (m.group(1), m.group(2))
            current_body = {}
            current_raw = [line]
            continue
        if current_header is None:
            continue  # pre-header content (file title, intro prose)
        current_raw.append(line)
        m = _BULLET_RE.match(line)
        if m:
            key = m.group(1).strip().lower().replace(" ", "_")
            current_body[key] = m.group(2).strip()
    _flush()
    return entries


def get_since(path: Path, since: str) -> list[dict]:
    """Return entries with timestamp >= ``since`` (ISO date or full timestamp).

    Lexicographic comparison on ISO timestamps is correct for UTC-Z dates,
    so this needs no datetime parsing. Empty / malformed ``since`` returns
    all entries.
    """
    entries = parse_file(path)
    cutoff = (since or "").strip()
    if not cutoff:
        return entries
    return [e for e in entries if e["timestamp"] >= cutoff]


def append_entry(
    path: Path,
    *,
    category: str,
    decision: str,
    why: str,
    atom_uid: Optional[str] = None,
    source_chunk_id: Optional[int] = None,
    source_paper_id: Optional[str] = None,
    slug_hint: Optional[str] = None,
) -> dict:
    """Append a new structured entry to ``decisions.md``.

    Creates the file with a one-line header if it doesn't exist. Slug is
    derived from ``slug_hint`` if given, else from the first 6 words of
    ``decision``. Returns a dict summarizing the written entry.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(
            "# Decisions & Gotchas\n\n"
            "Append-only. Written by `mcp__paper-compiler__record_decision`.\n",
            encoding="utf-8",
        )

    timestamp = _now_iso()
    if slug_hint:
        slug = _slugify(slug_hint)
    else:
        # Use the first few content words from `decision`.
        slug = _slugify(" ".join((decision or "").split()[:6]))

    lines: list[str] = [
        "",  # blank separator
        f"## {timestamp} · {slug}",
        f"**Category:** {category}",
    ]
    if atom_uid:
        lines.append(f"**Atom:** atom_uid {atom_uid}")
    lines.append(f"**Decision:** {decision.strip()}")
    lines.append(f"**Why:** {why.strip()}")
    if source_chunk_id is not None or source_paper_id:
        bits: list[str] = []
        if source_chunk_id is not None:
            bits.append(f"chunk_id={source_chunk_id}")
        if source_paper_id:
            bits.append(f"paper_id={source_paper_id}")
        lines.append("**Source:** " + ", ".join(bits))

    with path.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
        fh.write("\n")

    return {
        "ok": True,
        "timestamp": timestamp,
        "slug": slug,
        "category": category,
        "atom_uid": atom_uid,
    }
