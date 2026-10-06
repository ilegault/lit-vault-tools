"""Scan saved paper notes and write notes safely.

WHY THIS EXISTS
---------------
Invariants 1 and 2: the developer types into these notes by hand, so this module
is the single place that touches note files, and it never renames, moves or
deletes one. Files are read and written with `newline=""` so a CRLF note keeps
its CRLF bytes; any translation would silently rewrite the developer's file.

`write_note` is a no-op (no write, mtime untouched) when the text is unchanged,
which keeps re-runs idempotent (invariant 4). Otherwise it writes a temp file in
the same directory and `os.replace`s it over the note, so a crash leaves either
the old or the new bytes, never a half-written note, and the temp file is removed
on failure.

Scanning skips `_explore/` (temporary stubs, not saved papers) and any dot
directory (`.obsidian/`, `.git/`). A file that is not valid UTF-8 is skipped with
a warning: it could not be written back byte-for-byte.
"""

from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from lit_vault_tools.config import EXPLORE_DIR
from lit_vault_tools.domain.doi import PaperIds, normalize_doi
from lit_vault_tools.domain.frontmatter import read_scalar, split_note

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SavedNote:
    path: Path
    text: str
    ids: PaperIds


def _read(path: Path) -> str:
    with open(path, encoding="utf-8", newline="") as handle:
        return handle.read()


def _skipped(relative: Path) -> bool:
    dirs = relative.parts[:-1]
    if dirs and dirs[0] == EXPLORE_DIR:
        return True
    return any(part.startswith(".") for part in dirs)


def scan_saved_notes(vault: Path) -> list[SavedNote]:
    """Every `type: paper` note under `vault`, in sorted path order."""
    vault = Path(vault)
    found: list[SavedNote] = []
    for path in sorted(vault.rglob("*.md")):
        if not path.is_file() or _skipped(path.relative_to(vault)):
            continue
        try:
            text = _read(path)
        except UnicodeDecodeError:
            logger.warning("skipping %s: not valid UTF-8", path)
            continue
        parts = split_note(text)
        if read_scalar(parts, "type") != "paper":
            continue
        found.append(
            SavedNote(
                path=path,
                text=text,
                ids=PaperIds(
                    doi=normalize_doi(read_scalar(parts, "doi")),
                    openalex_id=read_scalar(parts, "openalex_id"),
                    s2_id=read_scalar(parts, "s2_id"),
                ),
            )
        )
    return found


def write_note(path: Path, text: str) -> bool:
    """Write `text` to `path` atomically. False (and no write) if unchanged."""
    path = Path(path)
    try:
        if _read(path) == text:
            return False
    except (FileNotFoundError, UnicodeDecodeError):
        pass
    fd, temp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise
    return True
