"""`enrich`: fill graph metadata into saved paper notes from OpenAlex.

WHY THIS EXISTS
---------------
Wires clients -> domain -> vault for the permanent library graph. This ticket's
slice writes only `openalex_id`, `oa_status`, `countries`, `enrich_status` and
`enriched_on`, always through `domain.frontmatter.apply_enrichment`, so every
line the script does not own and the whole body stay byte-identical (invariant 1).

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
"""

from __future__ import annotations

import datetime
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from lit_vault_tools.clients import openalex
from lit_vault_tools.clients.http import ClientError, Transport
from lit_vault_tools.domain.doi import normalize_doi
from lit_vault_tools.domain.frontmatter import apply_enrichment, read_scalar, split_note
from lit_vault_tools.vault.notes import scan_saved_notes, write_note

logger = logging.getLogger(__name__)


@dataclass
class EnrichSummary:
    ok: int = 0
    no_doi: int = 0
    not_found: int = 0
    error: int = 0

    def record(self, status: str) -> None:
        setattr(self, status, getattr(self, status) + 1)


def _read(path: Path) -> str:
    with open(path, encoding="utf-8", newline="") as handle:
        return handle.read()


def run_enrich(
    vault: Path,
    notes: Sequence[Path] | None,
    api_key: str,
    transport: Transport,
    today: datetime.date,
) -> EnrichSummary:
    """Enrich `notes` (every saved paper in `vault` when None); returns status counts."""
    paths = [note.path for note in scan_saved_notes(vault)] if notes is None else [Path(n) for n in notes]
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
        status, values = _lookup(read_scalar(parts, "doi"), api_key, transport, path)
        summary.record(status)
        if values is None:
            continue
        write_note(path, apply_enrichment(parts, values, today).render())
    return summary


def _lookup(raw_doi: str | None, api_key: str, transport: Transport, path: Path):
    """(status, values to write or None to leave the note untouched)."""
    doi = normalize_doi(raw_doi)
    if doi is None:
        return "no_doi", {"enrich_status": "no_doi"}
    try:
        record = openalex.fetch_work(doi, api_key, transport)
    except ClientError as err:
        logger.warning("enrich failed for %s: %s", path, err)
        return "error", None
    if record is None:
        return "not_found", {"enrich_status": "not_found"}
    return "ok", {
        "openalex_id": record.openalex_id,
        "oa_status": record.oa_status,
        "countries": record.countries,
        "enrich_status": "ok",
    }
