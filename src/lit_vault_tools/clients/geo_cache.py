"""On-disk cache of institution coordinates, kept outside the vault.

WHY THIS EXISTS
---------------
OpenAlex work responses carry dehydrated institutions (no coordinates), so geo
needs one extra request per institution. Institutions repeat across papers, so
the answers are cached in `institutions.json`.

* Decision 13: the cache lives outside the vault so it never syncs to the phone.
  Order: `LIT_VAULT_CACHE_DIR`, `%LOCALAPPDATA%/lit-vault-tools`,
  `$XDG_CACHE_HOME/lit-vault-tools`, `~/.cache/lit-vault-tools`.
* A `None` result is never cached, so an institution whose location OpenAlex
  fills in later can still be found (invariant 6: unknown is omitted, not 0,0).
* A corrupt cache file is a cache, not data: it is treated as empty and
  rewritten valid rather than failing a run.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path

_CACHE_FILE = "institutions.json"
_APP_DIR = "lit-vault-tools"

Geo = tuple[float, float]


def resolve_cache_dir() -> Path:
    override = os.environ.get("LIT_VAULT_CACHE_DIR")
    if override:
        return Path(override)
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / _APP_DIR
    xdg = os.environ.get("XDG_CACHE_HOME")
    if xdg:
        return Path(xdg) / _APP_DIR
    return Path.home() / ".cache" / _APP_DIR


def _load(path: Path) -> tuple[dict[str, list[float]], bool]:
    """Return (cache, was_valid). A missing file is a valid empty cache."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, True
    except (OSError, ValueError):
        return {}, False
    return (data, True) if isinstance(data, dict) else ({}, False)


def _save(path: Path, cache: dict[str, list[float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def get_institution_geo(institution_id: str, fetch: Callable[[str], Geo | None], cache_dir: Path) -> Geo | None:
    path = cache_dir / _CACHE_FILE
    cache, valid = _load(path)
    hit = cache.get(institution_id)
    if isinstance(hit, list) and len(hit) == 2:
        return float(hit[0]), float(hit[1])
    geo = fetch(institution_id)
    if geo is not None:
        cache[institution_id] = [geo[0], geo[1]]
    if geo is not None or not valid:
        _save(path, cache)
    return geo
