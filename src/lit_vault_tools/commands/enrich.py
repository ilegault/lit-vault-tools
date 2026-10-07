"""`enrich`: fill graph metadata into saved paper notes from OpenAlex (with fallbacks).

WHY THIS EXISTS
---------------
Wires clients -> domain -> vault for the permanent library graph. A paper note
gets `openalex_id`, `oa_status`, `countries`, `authors`, `institutions`,
`subfield`, `enrich_status` and `enriched_on`, always through
`domain.frontmatter.apply_enrichment`, so every line the script does not own and
the whole body stay byte-identical (invariant 1).

Statuses (`enrich_status`):
* `ok`        OpenAlex knew the DOI; values written.
* `partial`   only a fallback knew the paper: Crossref (OpenAlex 404 on a DOI, needs
              `CROSSREF_MAILTO`) or OSTI (no DOI; searched by the note's `title`).
              No OpenAlex data is written; the fallback record is kept in
              `EnrichSummary.records` so the linking step can use its reference DOIs.
* `no_doi`    no usable `doi` and OSTI did not find the title either.
* `not_found` OpenAlex 404 and no fallback had it (or Crossref was skipped).
* `error`     a `ClientError` (OpenAlex or a fallback); the note is left untouched (nothing is recorded
              about a transient failure) and the run continues, so one bad note
              or a rate limit never blocks the rest.

`s2_id` is looked up by DOI when `S2_API_KEY` is set. It is a convenience for
Explore, so a missing Semantic Scholar record or a `ClientError` just leaves
`s2_id` out; it never changes the status. One `Pacer` is shared by every S2 call
in the run so requests stay spaced across notes.

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

Saved-paper links
-----------------
After the per-note phase, `refs` is set on every note fetched this run by matching
its OpenAlex reference ids / reference DOIs against all saved papers (a second
pass, so a paper that only got its `openalex_id` this run can still be matched).
`cited_by` is then recomputed for every saved note as the inverse of all `refs`
in the vault, with no network, and written only when it differs. Only saved
papers ever appear; stale links disappear because `refs` is recomputed from the
current vault each time the note is enriched.

Finally `retire_stubs` deletes any stub in `_explore/` whose paper is now saved and
repoints its links to the real note (so saving a paper and running `enrich` is
all it takes).
"""

from __future__ import annotations

import datetime
import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from lit_vault_tools.clients import crossref, openalex, osti
from lit_vault_tools.clients.geo_cache import get_institution_geo, resolve_cache_dir
from lit_vault_tools.clients.http import ClientError, Transport
from lit_vault_tools.clients.semantic_scholar import Pacer, fetch_s2_paper_id
from lit_vault_tools.config import AUTHORS_DIR, INSTITUTIONS_DIR, SUBFIELDS_DIR
from lit_vault_tools.domain.doi import normalize_doi
from lit_vault_tools.domain.frontmatter import (
    apply_enrichment,
    read_list,
    read_scalar,
    set_key_line,
    split_note,
)
from lit_vault_tools.domain.links import cited_by_map, link_stem, make_link, resolve_refs
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
from lit_vault_tools.vault.retire import retire_stubs

logger = logging.getLogger(__name__)


@dataclass
class EnrichSummary:
    ok: int = 0
    partial: int = 0
    no_doi: int = 0
    not_found: int = 0
    error: int = 0
    # every record fetched this run (OpenAlex or fallback), by note path; `refs` is computed from these
    records: dict[Path, PaperRecord] = field(default_factory=dict)

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
    crossref_mailto: str | None = None
    s2_api_key: str | None = None
    s2_pacer: Pacer | None = None

    @classmethod
    def build(
        cls,
        vault: Path,
        api_key: str,
        transport: Transport,
        cache_dir: Path,
        crossref_mailto: str | None = None,
        s2_api_key: str | None = None,
        s2_pacer: Pacer | None = None,
    ) -> _Registry:
        registry = cls(
            vault,
            api_key,
            transport,
            cache_dir,
            scan_entity_notes(vault, AUTHORS_DIR),
            scan_entity_notes(vault, INSTITUTIONS_DIR),
            scan_entity_notes(vault, SUBFIELDS_DIR),
            crossref_mailto=crossref_mailto or None,
            s2_api_key=s2_api_key or None,
            s2_pacer=s2_pacer or Pacer(),
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
    crossref_mailto: str | None = None,
    s2_api_key: str | None = None,
    s2_pacer: Pacer | None = None,
) -> EnrichSummary:
    """Enrich `notes` (every saved paper in `vault` when None); returns status counts and fetched records."""
    vault = Path(vault)
    paths = [note.path for note in scan_saved_notes(vault)] if notes is None else [Path(n) for n in notes]
    registry = _Registry.build(
        vault, api_key, transport, cache_dir or resolve_cache_dir(), crossref_mailto, s2_api_key, s2_pacer
    )
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
        status, record, values = _lookup(registry, parts, path)
        summary.record(status)
        if values is None:
            continue
        if record is not None:
            summary.records[path] = record
            if status == "ok":
                values = {**values, **_link_people(registry, record)}
        write_note(path, apply_enrichment(parts, values, today).render())
    _write_refs(vault, summary.records, today)
    _write_cited_by(vault, today)
    retire_stubs(vault)
    return summary


def _write_refs(vault: Path, fetched: dict[Path, PaperRecord], today: datetime.date) -> None:
    """Set `refs` on each note fetched this run, matched against every saved paper (after phase one)."""
    if not fetched:
        return
    saved = scan_saved_notes(vault)
    candidates = [(note.path.stem, note.ids) for note in saved]
    for path, record in fetched.items():
        stems = resolve_refs(record.references, record.reference_dois, candidates, own=path.stem)
        parts = split_note(_read(path))
        write_note(path, apply_enrichment(parts, {"refs": [make_link(s) for s in stems]}, today).render())


def _write_cited_by(vault: Path, today: datetime.date) -> None:
    """Set `cited_by` on every saved note as the inverse of all saved notes' `refs`; no network."""
    saved = scan_saved_notes(vault)
    refs_by_stem = {
        note.path.stem: [link_stem(link) for link in read_list(split_note(note.text), "refs")] for note in saved
    }
    cited = cited_by_map(refs_by_stem)
    for note in saved:
        wanted = [make_link(stem) for stem in cited.get(note.path.stem, [])]
        parts = split_note(note.text)
        if read_list(parts, "cited_by") == wanted:
            continue
        write_note(note.path, apply_enrichment(parts, {"cited_by": wanted}, today).render())


def _lookup(registry: _Registry, parts, path: Path):
    """(status, record, values to write or None to leave the note untouched)."""
    doi = normalize_doi(read_scalar(parts, "doi"))
    try:
        if doi is None:
            status, record = _lookup_by_title(registry, read_scalar(parts, "title"))
        else:
            status, record = _lookup_by_doi(registry, doi)
    except ClientError as err:
        logger.warning("enrich failed for %s: %s", path, err)
        return "error", None, None
    values: dict[str, str | list[str] | None] = {"enrich_status": status}
    if status == "ok":
        values.update(
            openalex_id=record.openalex_id,
            oa_status=record.oa_status,
            countries=record.countries,
        )
    s2_id = _s2_id(registry, doi) if doi else None
    if s2_id:
        values["s2_id"] = s2_id
    return status, record, values


def _lookup_by_doi(registry: _Registry, doi: str):
    record = openalex.fetch_work(doi, registry.api_key, registry.transport)
    if record is not None:
        return "ok", record
    if registry.crossref_mailto:
        record = crossref.fetch_work(doi, registry.crossref_mailto, registry.transport)
        if record is not None:
            return "partial", record
    return "not_found", None


def _lookup_by_title(registry: _Registry, title: str | None):
    record = osti.fetch_by_title(title, registry.transport) if title else None
    return ("partial", record) if record is not None else ("no_doi", None)


def _s2_id(registry: _Registry, doi: str) -> str | None:
    """Semantic Scholar's id for `doi`; any failure just means no `s2_id` (it never changes the status)."""
    if not registry.s2_api_key:
        return None
    try:
        return fetch_s2_paper_id(doi, registry.s2_api_key, registry.transport, pacer=registry.s2_pacer)
    except ClientError as err:
        logger.warning("Semantic Scholar id lookup failed for %s: %s", doi, err)
        return None


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
