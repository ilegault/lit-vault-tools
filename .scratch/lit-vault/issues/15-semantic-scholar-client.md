# 15: Semantic Scholar client: paged neighbors and batch details

**Status:** ready-for-agent

**Runner:** any

**Auto-merge:** yes

**Blocked by:** 05, 06, 13

**Spec:** `CONTEXT.md` (repo root; there is no separate `spec.md`)
**Binding:** `docs/adr/0001-tests-first.md`; `CONTEXT.md` (the design); `AGENTS.md` sections 2-3 (layers, invariants, testing)

## What to build

Create `src/lit_vault_tools/clients/semantic_scholar.py` returning `Neighbor` values from `domain/neighbors.py`. API key goes where `tests/fixtures/README.md` records it (header `x-api-key`).

Functions: `fetch_s2_paper_id(doi, api_key, transport)`; `fetch_neighbors(paper_ref, relation, api_key, transport, sleep, clock)` which pages `/paper/<ref>/references` or `/citations` (`paper_ref` is `DOI:<doi>` or an `s2_id`) with the lean field set and `limit=1000`, following `offset` until `next` is absent; `fetch_details(s2_ids, api_key, transport, sleep, clock)` which POSTs `/paper/batch` in chunks of at most 500 ids for abstract, tldr, authors and venue. Requests are spaced at least 1 second apart using the injected `sleep` / `clock`. 404 and other non-success statuses raise `ClientError`; no retries.

Tests fake only the transport, replaying `s2_paper.json`, `s2_references_page1.json`, `s2_references_last.json`, `s2_citations_page1.json`, `s2_batch.json`. Read the fixtures for field paths (note references nest under `citedPaper`, citations under `citingPaper`).

## Acceptance criteria

- [ ] `fetch_neighbors(..., "reference", ...)` follows `next`: the fake transport serves page 1 then the last page; the result contains every item of both fixtures in order as `Neighbor`s with `relation == "reference"`, the lean fields from the fixture (`s2_id`, `title`, `year`, `citation_count`, `is_influential`, normalized `doi`), and `abstract`/`tldr` `None`. The second request uses the `offset` from the first response's `next`.
- [ ] The lean request asks for no abstract or tldr field and `limit=1000`; the test asserts the `fields` query value contains neither `abstract` nor `tldr`. `relation="citation"` reads `citingPaper` entries from `s2_citations_page1.json`.
- [ ] `fetch_details` with 1,203 fake ids issues three POSTs of 500, 500 and 203 ids, and returns a mapping `s2_id -> (abstract, tldr, authors, venue)` taken from `s2_batch.json` (replicate its entries under new ids to reach the count); ids the batch returns as `null` are absent from the mapping.
- [ ] Rate spacing: with a fake clock and fake `sleep`, three consecutive requests sleep so that no two requests start less than 1.0 second apart; the key never appears in a `ClientError` message or any log record.
- [ ] `fetch_s2_paper_id` returns the id in `s2_paper.json`; a 404 returns `None`; a 429 raises `ClientError` with status 429.

## Gate

```
ruff check .
python scripts/check_tests_first.py
pytest -q
```

CI (`.github/workflows/tests.yml`) runs exactly these, with `PYTHONUTF8=1` and bogus `OPENALEX_API_KEY` / `S2_API_KEY`. Zero failures before pushing.

## Comments
