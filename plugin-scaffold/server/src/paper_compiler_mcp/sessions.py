"""Parse and append entries in ``research/sessions/<YYYY-MM-DD>-<slug>.md``.

Session notes are written by the Stop hook at session end. Each file is one
session: started/ended timestamps, atoms touched, files modified, decisions
referenced, and a "next steps" stub the user (or `continue` sub-skill) can
fill in.

The shape is loose markdown — humans edit these between sessions to add
"next steps" notes — but the headers are stable so this parser can pull
out structured fields without an LLM call.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Optional

# File-naming convention: <YYYY-MM-DD>-<slug>(-<n>)?.md
_FILENAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-(.+?)(?:-(\d+))?\.md$")

# Section headers inside a session file.
_H1_RE = re.compile(r"^#\s+Session\s+(\S+)\s+—\s+(.+?)\s*$")
_H2_RE = re.compile(r"^##\s+(.+?)\s*$")
_FIELD_RE = re.compile(r"^\*\*([A-Za-z][A-Za-z _-]*):\*\*\s*(.*)$")
_BULLET_RE = re.compile(r"^\s*[-*]\s+`?([^`]+?)`?\s*(?:—\s*(.+))?$")


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime())


def _today_slug() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def _safe_slug(slug: str) -> str:
    s = (slug or "").lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "session"


def list_files(sessions_dir: Path, limit: int = 5) -> list[dict]:
    """Return up to ``limit`` session-file metadata entries, newest first.

    Each entry: ``{session_id, date, slug, path, atoms_touched, has_next_steps}``.
    Fast: stat + filename regex + a single grep per file for the headers we care
    about. No full parse.
    """
    if not sessions_dir.exists():
        return []
    paths = sorted(
        sessions_dir.glob("*.md"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[: max(0, int(limit))]

    out: list[dict] = []
    for p in paths:
        m = _FILENAME_RE.match(p.name)
        if not m:
            continue
        date, slug, _ = m.groups()
        session_id = p.stem  # filename without .md is the canonical id
        # Cheap parse: count atoms-touched bullets and check next-steps presence.
        atoms_count = 0
        has_next = False
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            text = ""
        in_atoms = False
        in_next = False
        for line in text.splitlines():
            h = _H2_RE.match(line)
            if h:
                title = h.group(1).strip().lower()
                in_atoms = title.startswith("atoms touched")
                in_next = title.startswith("next steps")
                continue
            if in_atoms and _BULLET_RE.match(line):
                # Skip the placeholder "(none detected)" line.
                if "_(none detected" not in line and "_(none_)" not in line:
                    atoms_count += 1
            if in_next and _BULLET_RE.match(line):
                if "_(left for the user" not in line:
                    has_next = True
        out.append({
            "session_id": session_id,
            "date": date,
            "slug": slug,
            "path": str(p),
            "atoms_touched": atoms_count,
            "has_next_steps": has_next,
        })
    return out


def parse_file(path: Path) -> Optional[dict]:
    """Parse one session file into a structured dict.

    Returns None if the file doesn't exist or has no parsable H1 header.
    """
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None

    title = ""
    title_slug = ""
    fields: dict[str, str] = {}
    sections: dict[str, list[str]] = {}
    current_section: Optional[str] = None

    for line in text.splitlines():
        m1 = _H1_RE.match(line)
        if m1:
            title_slug = m1.group(2).strip()
            title = f"Session {m1.group(1)} — {title_slug}"
            current_section = None
            continue
        m2 = _H2_RE.match(line)
        if m2:
            current_section = m2.group(1).strip().lower()
            sections.setdefault(current_section, [])
            continue
        mf = _FIELD_RE.match(line)
        if mf and current_section is None:
            # **Key:** value at file top
            key = mf.group(1).strip().lower().replace(" ", "_")
            fields[key] = mf.group(2).strip()
            continue
        if current_section is not None:
            sections[current_section].append(line)

    def _bullets(section_name: str) -> list[str]:
        out_b: list[str] = []
        for raw in sections.get(section_name, []):
            m = _BULLET_RE.match(raw)
            if not m:
                continue
            val = m.group(1).strip()
            if "_(none detected" in val or "_(left for the user" in val:
                continue
            out_b.append(val)
        return out_b

    return {
        "session_id": path.stem,
        "title": title,
        "title_slug": title_slug,
        "started": fields.get("started"),
        "ended": fields.get("ended"),
        "paper": fields.get("paper"),
        "session_id_field": fields.get("session_id"),
        "atoms_touched": _bullets("atoms touched"),
        "files_modified": _bullets("files modified"),
        "decisions_recorded": _bullets("decisions recorded"),
        "next_steps": _bullets("next steps"),
    }


def append_note(
    sessions_dir: Path,
    *,
    session_id: Optional[str] = None,
    note: str,
    kind: str = "atom_touched",
) -> dict:
    """Append a one-line note to the latest (or named) session file.

    ``kind`` ∈ {"atom_touched", "file_modified", "decision_referenced",
    "next_step"} controls which section the line lands under. If
    ``session_id`` is omitted, picks the newest session file. If no session
    file exists, creates a fresh one for today.
    """
    sessions_dir.mkdir(parents=True, exist_ok=True)
    section_map = {
        "atom_touched": "Atoms touched",
        "file_modified": "Files modified",
        "decision_referenced": "Decisions recorded",
        "next_step": "Next steps",
    }
    section = section_map.get(kind, "Atoms touched")

    if session_id:
        path = sessions_dir / f"{session_id}.md"
        if not path.exists():
            return {"ok": False, "reason": f"session {session_id} not found"}
    else:
        # Newest, or create.
        existing = sorted(sessions_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        if existing:
            path = existing[0]
        else:
            slug = _safe_slug(f"{_now_iso()}-adhoc")
            path = sessions_dir / f"{_today_slug()}-adhoc.md"
            path.write_text(
                f"# Session {_today_slug()} — adhoc\n"
                f"**Ended:** {_now_iso()}\n\n"
                f"## Atoms touched\n\n## Files modified\n\n"
                f"## Decisions recorded\n\n## Next steps\n",
                encoding="utf-8",
            )

    # Append the note under the right section. Re-write the file with the
    # bullet appended to the right H2 block.
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    out_lines: list[str] = []
    appended = False
    in_target = False
    section_lower = section.lower()

    bullet_text = note.strip()
    bullet = f"- `{bullet_text}`" if kind in {"atom_touched", "file_modified"} else f"- {bullet_text}"

    for i, line in enumerate(lines):
        out_lines.append(line)
        m = _H2_RE.match(line)
        if m:
            if in_target and not appended:
                # We just left the target section without appending; do it now.
                out_lines.insert(len(out_lines) - 1, bullet)
                appended = True
            in_target = (m.group(1).strip().lower() == section_lower)

    # If file ended while in target section and we never inserted, append at end.
    if in_target and not appended:
        # Drop trailing empty line if any, append bullet, restore newline.
        while out_lines and out_lines[-1] == "":
            out_lines.pop()
        out_lines.append(bullet)
        appended = True

    if not appended:
        # Section header wasn't present; create one at the end.
        out_lines.extend(["", f"## {section}", bullet])

    path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    return {
        "ok": True,
        "session_id": path.stem,
        "section": section,
        "note": bullet_text,
    }
