"""The `_explore/` folder: the only place anything is deleted, and only inside it.

WHY THIS EXISTS
---------------
Invariant 2: a saved paper note is never renamed, moved or deleted; the only
deletions in the whole project are the temporary stubs in `_explore/`. Keeping
`wipe_explore` and `write_stub` in one small module makes that boundary easy to
audit: nothing here ever builds a path outside `<vault>/_explore`.

`wipe_explore` empties the folder but keeps (or creates) it, so a caller can
always write straight after. `keep` names stub files (by stem) that survive the
wipe: the trail's foci, whose own notes must outlive the clearing of their
neighbours (CONTEXT.md, Stub lifecycle 5). Explore calls it only after everything has been
fetched, so a failed fetch never costs the developer the previous session.
"""

from __future__ import annotations

import shutil
from collections.abc import Collection
from pathlib import Path

from lit_vault_tools.config import EXPLORE_DIR
from lit_vault_tools.vault.notes import write_note


def explore_path(vault: Path) -> Path:
    return Path(vault) / EXPLORE_DIR


def wipe_explore(vault: Path, keep: Collection[str] = ()) -> Path:
    """Delete everything inside `<vault>/_explore/` except `<stem>.md` for each stem in `keep`.

    Creates the folder if missing; returns it.
    """
    root = explore_path(vault)
    root.mkdir(parents=True, exist_ok=True)
    kept = {f"{stem}.md" for stem in keep}
    for child in root.iterdir():
        if child.name in kept and child.is_file():
            continue
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()
    return root


def write_stub(vault: Path, stem: str, text: str) -> Path:
    """Write `<vault>/_explore/<stem>.md` atomically; returns its path."""
    path = explore_path(vault) / f"{stem}.md"
    write_note(path, text)
    return path
