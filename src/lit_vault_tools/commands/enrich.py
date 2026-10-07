"""`enrich`: fill graph metadata into saved paper notes from OpenAlex.

WHY THIS EXISTS
---------------
Wires clients -> domain -> vault for the permanent library graph. A paper note
gets `openalex_id`, `oa_status`, `countries`, `authors`, `institutions`,
`subfield`, `enrich_status` and `enriched_on`, always through
`domain.frontmatter.apply_enrichment`, so every line the script does not own and
the whole body stay byte-identical (invariant 1).

Statuses (`enrich_status`):
* `ok`        OpenAlex knew the DOI; values written.
* `no_doi`    the note has no usable `doi`; nothing to look up.
* `not_found` OpenAlex answered 404.
* `error`     a `ClientError`; the note is left untouched (nothing is recorded
              about a transient failure) and the run continues, so one bad note
              or a rate limit never blocks the rest.

Only `type: paper` notes are processed, even when a path is named explicitly: an
author note or stub must never gain enrichment keys. Re-running is a no-op
(invariant 4): `apply_enrichment` keeps `enriched_on` unless a value changed and
`write_note` skips an unchanged write.

People and places
-----------------
Each author, institution and subfield gets a note in `Authors/`, `Institutions/`,
`Subfields/`. Identity is the `openalex_id` in the target note's frontmatter
(`vault.notes.scan_entity_notes`), never its filename (invariant 3):

* a note the developer renamed by hand is found by id and linked under its new
  name; nothing is renamed, moved or duplicated (invariant 2);
* an existing note's body is never touched. Only `aliases` (authors; entries are
  added, never removed, so the developer's own aliases survive) and a missing
  `location` (institutions) are edited, line-wise, via `set_key_line`;
* a new author gets a filename from `assign_author_filenames`, which is told the
  developer's own id-less notes are taken names, so they are never overwritten;
* an unknown location is omitted, never `0,0` (invariant 6); it is not cached, so
  a later run can add it. A geo lookup that fails must not fail the paper.
"""

from __future__ import annotations

import datetime
import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from lit_vault_tools.clients import openalex
from lit_vault_tools.clients.geo_cache import get_institution_geo, resolve_cache_dir
from lit_vault_tools.clients.http import ClientError, Transport
from lit_vault_tools.config import AUTHORS_DIR, INSTITUTIONS_DIR, SUBFIELDS_DIR
from lit_vault_tools.domain.doi import normalize_doi
from lit_vault_tools.domain.frontmatter import (
    apply_enrichment,
    read_list,
    read_scalar,
    set_key_line,
    split_note,
)
from lit_vault_tools.domain.paper_record import PaperRecord
from lit_vault_tools.domain.people import (
    InstitutionRef,
    assign_author_filenames,
    institution_location,
    merge_aliases,
    render_author_note,
    render_institution_note,
    render_subfield_note,
    sanitize_filename,
)
from lit_vault_tools.vault.notes import EntityIndex, scan_entity_notes, scan_saved_notes, write_note

logger = logging.getLogger(__name__)


@dataclass
class EnrichSummary:
    ok: int = 0
    no_doi: int = 0
    not_found: int = 0
    error: int = 0

    def record(self, status: str) -> None:
        setattr(self, status, getattr(self, status) + 1)


@dataclass
class _Registry:
    """Per-run view of the Authors/Institutions/Subfields folders, kept current as notes are created."""

    vault: Path
    api_key: str
    transport: Transport
    cache_dir: Path
    authors: EntityIndex
    institutions: EntityIndex
    subfields: EntityIndex
    author_stems: dict[str, str] = field(default_factory=dict)
    taken: dict[str, set[str]] = field(default_factory=dict)

    @classmethod
    def build(cls, vault: Path, api_key: str, transport: Transport, cache_dir: Path) -> _Registry:
        registry = cls(
            vault,
            api_key,
            transport,
            cache_dir,
            scan_entity_notes(vault, AUTHORS_DIR),
            scan_entity_notes(vault, INSTITUTIONS_DIR),
            scan_entity_notes(vault, SUBFIELDS_DIR),
        )
        # id -> stem for known authors; the developer's own id-less notes count as taken names.
        registry.author_stems = {i: p.stem for i, p in registry.authors.by_id.items()}
        registry.author_stems.update({f"file:{stem}": stem for stem in registry.authors.unidentified})
        registry.taken = {
            INSTITUTIONS_DIR: set(registry.institutions.stems),
            SUBFIELDS_DIR: set(registry.subfields.stems),
        }
        return registry


def _read(path: Path) -> str:
    with open(path, encoding="utf-8", newline="") as handle:
        return handle.read()


def run_enrich(
    vault: Path,
    notes: Sequence[Path] | None,
    api_key: str,
    transport: Transport,
    today: datetime.date,
    cache_dir: Path | None = None,
) -> EnrichSummary:
    """Enrich `notes` (every saved paper in `vault` when None); returns status counts."""
    vault = Path(vault)
    paths = [note.path for note in scan_saved_notes(vault)] if notes is None else [Path(n) for n in notes]
    registry = _Registry.build(vault, api_key, transport, cache_dir or resolve_cache_dir())
    summary = EnrichSummary()
    for path in paths:
        try:
            text = _read(path)
        except (OSError, UnicodeDecodeError) as err:
            logger.warning("skipping %s: %s", path, err)
            continue
        parts = split_note(text)
        if read_scalar(parts, "type") != "paper":
            logger.info("skipping %s: not a paper note", path)
            continue
        status, record, values = _lookup(read_scalar(parts, "doi"), api_key, transport, path)
        summary.record(status)
        if values is None:
            continue
        if record is not None:
            values = {**values, **_link_people(registry, record)}
        write_note(path, apply_enrichment(parts, values, today).render())
    return summary


def _lookup(raw_doi: str | None, api_key: str, transport: Transport, path: Path):
    """(status, record, values to write or None to leave the note untouched)."""
    doi = normalize_doi(raw_doi)
    if doi is None:
        return "no_doi", None, {"enrich_status": "no_doi"}
    try:
        record = openalex.fetch_work(doi, api_key, transport)
    except ClientError as err:
        logger.warning("enrich failed for %s: %s", path, err)
        return "error", None, None
    if record is None:
        return "not_found", None, {"enrich_status": "not_found"}
    return (
        "ok",
        record,
        {
            "openalex_id": record.openalex_id,
            "oa_status": record.oa_status,
            "countries": record.countries,
            "enrich_status": "ok",
        },
    )


def _link(stem: str) -> str:
    return f"[[{stem}]]"


def _link_people(registry: _Registry, record: PaperRecord) -> dict[str, list[str] | None]:
    """Create/update the people and place notes for `record`; return the link lists for the paper."""
    authors = _ensure_authors(registry, record)
    institutions = [_link(_ensure_institution(registry, inst)) for inst in record.institutions]
    subfield = _ensure_subfield(registry, record)
    return {
        "authors": authors,
        "institutions": institutions,
        "subfield": [_link(subfield)] if subfield else None,
    }


def _ensure_authors(registry: _Registry, record: PaperRecord) -> list[str]:
    seen = [(ref, names[0] if names else None) for ref, names in record.authors]
    registry.author_stems = assign_author_filenames(seen, registry.author_stems)
    links = []
    for ref, _ in record.authors:
        stem = registry.author_stems[ref.openalex_id]
        raw = record.author_raw_names.get(ref.openalex_id)
        variants = [raw] if raw else []
        path = registry.authors.by_id.get(ref.openalex_id)
        if path is None:
            path = registry.vault / AUTHORS_DIR / f"{stem}.md"
            registry.authors.by_id[ref.openalex_id] = path
            write_note(path, render_author_note(ref, merge_aliases([], variants, ref.display_name)))
        else:
            _add_aliases(path, variants, ref.display_name)
        links.append(_link(path.stem))
    return links


def _add_aliases(path: Path, variants: Sequence[str], display_name: str | None) -> None:
    """Append unseen name variants to an existing author note; never remove one."""
    parts = split_note(_read(path))
    current = read_list(parts, "aliases")
    additions = [name for name in merge_aliases([], variants, display_name) if name not in current]
    if additions:
        rendered = "[" + ", ".join(json.dumps(a, ensure_ascii=False) for a in [*current, *additions]) + "]"
        write_note(path, set_key_line(parts, "aliases", rendered).render())


def _free_stem(registry: _Registry, folder: str, name: str | None, openalex_id: str) -> str:
    stem = sanitize_filename(name or openalex_id)
    taken = registry.taken[folder]
    if stem.casefold() in taken:
        stem = f"{stem} ({openalex_id})"
    taken.add(stem.casefold())
    return stem


def _ensure_institution(registry: _Registry, institution: InstitutionRef) -> str:
    path = registry.institutions.by_id.get(institution.openalex_id)
    if path is None:
        stem = _free_stem(registry, INSTITUTIONS_DIR, institution.display_name, institution.openalex_id)
        path = registry.vault / INSTITUTIONS_DIR / f"{stem}.md"
        registry.institutions.by_id[institution.openalex_id] = path
        write_note(path, render_institution_note(institution, _location(registry, institution.openalex_id)))
        return stem
    parts = split_note(_read(path))
    if read_scalar(parts, "location") is None:
        location = _location(registry, institution.openalex_id)
        if location:
            write_note(path, set_key_line(parts, "location", location).render())
    return path.stem


def _location(registry: _Registry, institution_id: str) -> str | None:
    def fetch(identifier: str):
        try:
            return openalex.fetch_institution_geo(identifier, registry.api_key, registry.transport)
        except ClientError as err:
            logger.warning("institution geo lookup failed for %s: %s", identifier, err)
            return None

    geo = get_institution_geo(institution_id, fetch, registry.cache_dir)
    return institution_location(*geo) if geo else None


def _ensure_subfield(registry: _Registry, record: PaperRecord) -> str | None:
    if not record.subfield:
        return None
    if record.subfield_id and record.subfield_id in registry.subfields.by_id:
        return registry.subfields.by_id[record.subfield_id].stem
    name = sanitize_filename(record.subfield)
    if record.subfield_id is None and name.casefold() in registry.taken[SUBFIELDS_DIR]:
        return name  # no id to match by: the same-named note is the subfield
    stem = _free_stem(registry, SUBFIELDS_DIR, record.subfield, record.subfield_id or "")
    path = registry.vault / SUBFIELDS_DIR / f"{stem}.md"
    if record.subfield_id:
        registry.subfields.by_id[record.subfield_id] = path
    write_note(path, render_subfield_note(record.subfield, record.subfield_id))
    return stem
