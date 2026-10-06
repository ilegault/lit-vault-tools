# 11: Enrich: Crossref/OSTI fallbacks and s2_id

**Status:** ready-for-agent

**Runner:** any

**Auto-merge:** yes

**Blocked by:** 08, 09, 15

**Spec:** `CONTEXT.md` (repo root; there is no separate `spec.md`)
**Binding:** `docs/adr/0001-tests-first.md`; `CONTEXT.md` (the design); `AGENTS.md` sections 2-3 (layers, invariants, testing)

## What to build

Extend `src/lit_vault_tools/commands/enrich.py` to try fallbacks and to fill `s2_id`.

Flow per note: OpenAlex first. On OpenAlex 404 and a `doi`, try `clients.crossref.fetch_work` (`CROSSREF_MAILTO` from the environment or `.env`). On no `doi`, try `clients.osti.fetch_by_title` using the note's `title` (`read_scalar`). Fallback hits give `enrich_status: partial`; both missing gives `not_found` (with DOI) or `no_doi` (without). `s2_id` comes from `clients.semantic_scholar.fetch_s2_paper_id(doi)` when the note has a DOI (`S2_API_KEY`); a missing S2 record or `ClientError` leaves `s2_id` omitted and does not change the status.

Tests: temporary vault; fake transport routing by URL to `openalex_work.json`, `crossref_work.json`, `osti_record.json`, `s2_paper.json` and to 404s.

## Acceptance criteria

- [ ] OpenAlex 404 + Crossref hit: the note gets `enrich_status: partial`, no `openalex_id`, and its Zotero fields and body are byte-identical; the Crossref record (with its `reference_dois`) is available to the linking step: `EnrichSummary.records[<note path>]` equals the `PaperRecord` returned by the Crossref client (ticket 12 reads records from there; if `EnrichSummary` has no `records` mapping yet, add it).
- [ ] OpenAlex 404 + Crossref 404: `not_found`. No `doi` + OSTI hit: `partial`. No `doi` + OSTI empty: `no_doi`. Each case is a separate test asserting the note's `enrich_status` line.
- [ ] `s2_id` equals the id in `s2_paper.json` after an `ok` run, and a second run is byte-identical; with S2 returning 404 the note has no `s2_id` line and is still `ok`.
- [ ] Missing `CROSSREF_MAILTO` skips Crossref (the transport is never called for it) and the note stays `not_found`; no exception, no log record containing the mailto value.
- [ ] A `ClientError` from a fallback gives `enrich_status: error` with the note's bytes unchanged, and the run continues to the next note.

## Gate

```
ruff check .
python scripts/check_tests_first.py
pytest -q
```

CI (`.github/workflows/tests.yml`) runs exactly these, with `PYTHONUTF8=1` and bogus `OPENALEX_API_KEY` / `S2_API_KEY`. Zero failures before pushing.

## Comments
