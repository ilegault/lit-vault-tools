# 21: Semantic Scholar client: reference neighbors from a list of DOIs

**Status:** ready-for-agent

**Runner:** any

**Auto-merge:** yes

**Blocked by:** 15, 20

**Spec:** `CONTEXT.md` (repo root; there is no separate `spec.md`)
**Binding:** `docs/adr/0001-tests-first.md`; `CONTEXT.md` (the design); `AGENTS.md` sections 2-3 (layers, invariants, testing)

## What to build

Add `fetch_neighbors_by_doi(dois, api_key, transport, sleep, clock) -> list[Neighbor]` to `src/lit_vault_tools/clients/semantic_scholar.py`. Explore uses it (ticket 22) when Semantic Scholar hides a paper's reference list but Crossref has the reference DOIs (`CONTEXT.md` decision 17).

It POSTs `/paper/batch?fields=title,year,citationCount,externalIds` with body `{"ids": ["DOI:<doi>", ...]}`, at most 500 ids per POST, through the same request path as `fetch_details` from ticket 15 (spacing, 429 backoff, `x-api-key` header): call that shared helper, do not copy it. DOIs are normalized with `domain.doi.normalize_doi` and de-duplicated before sending. Each non-null entry becomes a `Neighbor` (`domain/neighbors.py`) with `relation="reference"`, `is_influential=False` (the batch endpoint has no such flag), `doi` normalized from `externalIds.DOI`, `abstract` and `tldr` `None`. Null entries (DOIs Semantic Scholar does not know) are skipped. Output order follows the input DOI order.

Tests fake only the transport, replaying `tests/fixtures/s2_batch_by_doi.json` (replicate its entries under new ids and DOIs to reach larger counts; the shape stays real). Read the fixture and its README entry for the exact request; do not guess field paths.

## Acceptance criteria

- [ ] Called with the four DOIs recorded in the fixture README, the result has one `Neighbor` per non-null fixture entry, in request order, with `s2_id`, `title`, `year`, `citation_count` and normalized `doi` equal to the fixture's values; the fake DOI is absent; every result has `relation == "reference"`, `is_influential is False`, `abstract is None`, `tldr is None`.
- [ ] The recorded request matches the fixture README: method `POST`, path `/graph/v1/paper/batch`, `fields` query value exactly `title,year,citationCount,externalIds` (asserted to contain neither `abstract` nor `tldr`), body `ids` each `DOI:` + normalized DOI, and the header name exactly `x-api-key` carrying the test key.
- [ ] 1,203 distinct DOIs produce three POSTs of 500, 500 and 203 ids; two input DOIs differing only in case or a `https://doi.org/` prefix are sent once and yield one `Neighbor`.
- [ ] An empty DOI list returns `[]` and the fake transport records no request.
- [ ] A transport answering 429 then the fixture succeeds after the fake `sleep` records a 5-second wait; the test key never appears in a `ClientError` message or any log record (`caplog`, all levels).

## Gate

```
ruff check .
python scripts/check_tests_first.py
pytest -q
```

CI (`.github/workflows/tests.yml`) runs exactly these, with `PYTHONUTF8=1` and bogus `OPENALEX_API_KEY` / `S2_API_KEY`. Zero failures before pushing.

## Comments
