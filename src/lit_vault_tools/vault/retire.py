"""Stub retirement: delete a stub whose paper has become a saved paper.

WHY THIS EXISTS
---------------
Saving a paper (adding it to Zotero, then `enrich`) makes it permanent, so a
temporary stub for it is now redundant and would show the same paper twice in the
graph. `retire_stubs` runs at the end of both `enrich` and `explore` and, for each
`type: stub` note, matches it to a saved paper by id (`find_paper`: DOI or
`s2_id`, never the filename, invariant 3), deletes the stub and repoints
`[[<stub stem>]]` to `[[<saved note stem>]]` in `_focus.md` and `_trail.md`.

Invariant 2: the only deletions anywhere are inside `_explore/`, and only stubs
sitting directly in it. A `type: stub` note elsewhere is the developer's, and a
saved paper note is never touched. Re-running changes nothing (invariant 4):
every write goes through `write_note`, which skips unchanged text.

Repointing can make the trail name the same note twice (the saved note was
already a focus); the later duplicate is dropped and the list renumbered.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from lit_vault_tools.domain.doi import find_paper
from lit_vault_tools.domain.frontmatter import read_scalar, split_note
from lit_vault_tools.domain.stubs import read_stub_ids
from lit_vault_tools.vault.explore_dir import explore_path
from lit_vault_tools.vault.notes import scan_saved_notes, write_note

logger = logging.getLogger(__name__)

_LINK_FILES = ("_focus.md", "_trail.md")
_TRAIL_ITEM = re.compile(r"^(\s*)\d+\.(\s*)(\[\[.+?\]\].*)$")


def retire_stubs(vault: Path) -> list[str]:
    """Retire every stub that matches a saved paper; returns the retired stub stems (sorted)."""
    root = explore_path(vault)
    if not root.is_dir():
        return []
    saved = scan_saved_notes(vault)
    if not saved:
        return []
    candidates = [note.ids for note in saved]
    retired: dict[str, str] = {}
    for path in sorted(root.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if read_scalar(split_note(text), "type") != "stub":
            continue
        match = find_paper(read_stub_ids(text), candidates)
        if match is None:
            continue
        retired[path.stem] = saved[match].path.stem
        path.unlink()
        logger.info("retired stub %s -> saved note %s", path.stem, saved[match].path.stem)
    if retired:
        for name in _LINK_FILES:
            _repoint(root / name, retired)
    return sorted(retired)


def _repoint(path: Path, retired: dict[str, str]) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return
    new = text
    for stub_stem, saved_stem in retired.items():
        new = re.sub(r"\[\[" + re.escape(stub_stem) + r"(?=\]\]|\||#)", lambda _m, s=saved_stem: f"[[{s}", new)
    if path.name == "_trail.md":
        new = _dedupe_trail(new)
    write_note(path, new)


def _dedupe_trail(text: str) -> str:
    """Drop a repeated trail entry (keeping the newest) and renumber."""
    out: list[str] = []
    seen: set[str] = set()
    number = 0
    for line in text.splitlines(keepends=True):
        match = _TRAIL_ITEM.match(line.rstrip("\r\n"))
        if match is None:
            out.append(line)
            continue
        link = re.match(r"\[\[(.+?)\]\]", match.group(3)).group(1)
        if link in seen:
            continue
        seen.add(link)
        number += 1
        eol = line[len(line.rstrip("\r\n")) :]
        out.append(f"{match.group(1)}{number}.{match.group(2)}{match.group(3)}{eol}")
    return "".join(out)
