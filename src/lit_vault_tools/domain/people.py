"""Author, institution and subfield naming and rendering: pure functions.

WHY THIS EXISTS
---------------
Authors are hard because display names collide ("J. Smith"). Invariant 3 says
identity is the OpenAlex author ID, never the name, so the filename is only a
readable graph label and is made unique here, never used for matching.

* `assign_author_filenames` is stable: filenames already in `existing` are never
  changed or reused, so processing authors in a different order cannot rename
  a note the developer already has. Collisions are judged case-insensitively
  because Windows filesystems are.
* `merge_aliases` only appends, so re-running adds nothing new.
* `institution_location` returns None rather than "0,0" (invariant 6): a missing
  coordinate must omit the `location:` line, not pin the institution off Africa.
* Rendered notes carry only frontmatter and an empty body; these notes are
  created once and the developer owns anything typed into them afterwards.
  Output is deterministic (invariant 4).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

_FORBIDDEN = '\\/:*?"<>|'
_UNNAMED = "Unnamed"


@dataclass(frozen=True)
class AuthorRef:
    openalex_id: str
    display_name: str | None = None


@dataclass(frozen=True)
class InstitutionRef:
    openalex_id: str
    display_name: str | None = None
    ror: str | None = None
    country: str | None = None
    institution_type: str | None = None


def sanitize_filename(name: str | None) -> str:
    """Windows-safe filename stem: forbidden characters become `-`, trailing dots/spaces go."""
    text = "".join("-" if ch in _FORBIDDEN or ord(ch) < 32 else ch for ch in (name or ""))
    text = text.rstrip(". ").lstrip()
    return text or _UNNAMED


def assign_author_filenames(
    seen: Sequence[tuple[AuthorRef, str | None]],
    existing: Mapping[str, str],
) -> dict[str, str]:
    """Map every author id (existing and newly seen) to a unique filename stem.

    `seen` pairs each author with an institution display name used to
    disambiguate (or None). Ids already in `existing` keep their filename.
    A new author whose name is taken gets ` (<institution>)`; if that is taken
    too (or there is no institution), ` (2)`, ` (3)`, ... is appended.
    """
    result = dict(existing)
    taken = {name.casefold() for name in result.values()}
    for author, institution in seen:
        if author.openalex_id in result:
            continue
        base = sanitize_filename(author.display_name)
        candidate = base
        if candidate.casefold() in taken and institution:
            candidate = f"{base} ({sanitize_filename(institution)})"
        stem = candidate
        counter = 2
        while candidate.casefold() in taken:
            candidate = f"{stem} ({counter})"
            counter += 1
        result[author.openalex_id] = candidate
        taken.add(candidate.casefold())
    return result


def merge_aliases(existing: Iterable[str], seen_names: Iterable[str], display_name: str | None) -> list[str]:
    """Existing aliases in order, then unseen variants in first-seen order; never `display_name`."""
    merged: list[str] = []
    for name in (*existing, *seen_names):
        if name and name != display_name and name not in merged:
            merged.append(name)
    return merged


def institution_location(lat: float | None, lng: float | None) -> str | None:
    """`"lat,lng"` for known coordinates; None if either is missing or both are 0."""
    if lat is None or lng is None or (lat == 0 and lng == 0):
        return None
    return f"{lat},{lng}"


def _quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _note(lines: list[str]) -> str:
    return "---\n" + "".join(line + "\n" for line in lines) + "---\n"


def render_author_note(author: AuthorRef, aliases: Sequence[str]) -> str:
    return _note(
        [
            "type: author",
            f"openalex_id: {_quote(author.openalex_id)}",
            "aliases: [" + ", ".join(_quote(a) for a in aliases) + "]",
        ]
    )


def render_institution_note(institution: InstitutionRef, location: str | None) -> str:
    lines = ["type: institution", f"openalex_id: {_quote(institution.openalex_id)}"]
    if institution.ror:
        lines.append(f"ror: {_quote(institution.ror)}")
    if institution.country:
        lines.append(f"country: {_quote(institution.country)}")
    if institution.institution_type:
        lines.append(f"institution_type: {_quote(institution.institution_type)}")
    if location:
        # Map View format, deliberately unquoted: `location: lat,lng`.
        lines.append(f"location: {location}")
    return _note(lines)


def render_subfield_note(display_name: str, openalex_id: str | None = None) -> str:
    """Subfield notes are named by the caller; `display_name` is only used for the filename upstream."""
    lines = ["type: subfield"]
    if openalex_id:
        lines.append(f"openalex_id: {_quote(openalex_id)}")
    return _note(lines)
