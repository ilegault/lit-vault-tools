# 05: Capture real API responses into tests/fixtures/

**Status:** done

**Runner:** developer

**Auto-merge:** no

**Blocked by:** None (can start immediately)

**Spec:** `CONTEXT.md` (repo root; there is no separate `spec.md`)
**Binding:** `CONTEXT.md` decision 15; `AGENTS.md` section 3 (fixtures are real)

## What to build

A person must do this: it needs the live `OPENALEX_API_KEY` / `S2_API_KEY` and network, which an agent must never use (`AGENTS.md` protocol rule 10).

Pick one real, well-cited ion-irradiation / nuclear-materials paper with a DOI that is in Crossref, OpenAlex and Semantic Scholar, with at least one reference and one citation. Save the **unmodified** JSON of each response into `tests/fixtures/` under the names below. OpenAlex is CC0.

Files: `openalex_work.json` (work by DOI), `openalex_institution.json` (one institution from that work, fetched by its id), `s2_paper.json` (`/paper/DOI:<doi>?fields=paperId`), `s2_references_page1.json` (a page that has `next`; use `limit` small, for example 5), `s2_references_last.json` (the final page, no `next`), `s2_citations_page1.json`, `s2_batch.json` (POST `/paper/batch` with the fields for abstract, tldr, authors, venue), `crossref_work.json` (a work that has a `reference` array), `osti_record.json` (one DOE technical report found by title).

Also write `tests/fixtures/README.md`: for each file, the exact request (method, URL with the key replaced by `<KEY>`, how the key was passed: header or query parameter, and any request body) and the capture date. Later tickets build their requests exactly as recorded there.

## Acceptance criteria

- [x] All nine files exist under `tests/fixtures/` and each parses as JSON.
- [x] No file or README line contains an API key, a mailto address, or any personal name or email (grep for the key values and for `@`).
- [x] `tests/fixtures/README.md` lists every file with its exact request and capture date, and states how each API expects the key.
- [x] `s2_references_page1.json` has a `next` field and `s2_references_last.json` does not; `openalex_work.json` has at least one entry in `referenced_works`; `crossref_work.json` has a non-empty `reference` array.
- [x] Set the ticket `Status: done` after committing the fixtures on a branch and opening a PR.

## Gate

```
ruff check .
python scripts/check_tests_first.py
pytest -q
```

CI (`.github/workflows/tests.yml`) runs exactly these, with `PYTHONUTF8=1` and bogus `OPENALEX_API_KEY` / `S2_API_KEY`. Zero failures before pushing.

## Comments

2026-10-06: Captured with `scripts/capture_fixtures.py` (merged in PR #7) against DOI `10.1016/j.matdes.2024.112730` (open access). Also saved `s2_references_elided.json`: a paywalled paper whose references Semantic Scholar hides (`"data": null`). Two findings fed back into the plan: Python's `urllib` re-capitalises header names, so the case-sensitive `x-api-key` was never recognised (ticket 06 amended to `http.client`); and paywalled papers' references are hidden on Semantic Scholar (tickets 15, 20-22).
