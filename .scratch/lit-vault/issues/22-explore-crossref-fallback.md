# 22: Explore: fall back to Crossref when Semantic Scholar hides references

**Status:** ready-for-agent

**Runner:** any

**Auto-merge:** yes

**Blocked by:** 08, 16, 21

**Spec:** `CONTEXT.md` (repo root; there is no separate `spec.md`)
**Binding:** `docs/adr/0001-tests-first.md`; `CONTEXT.md` (the design); `AGENTS.md` sections 2-3 (layers, invariants, testing)

## What to build

Extend `run_explore` in `src/lit_vault_tools/commands/explore.py` (`CONTEXT.md` decision 17). When `clients.semantic_scholar.fetch_neighbors(..., "reference", ...)` raises `ReferencesHidden`, Explore calls `clients.crossref.fetch_work(focus_doi, mailto, transport)`, takes its `reference_dois`, and calls `clients.semantic_scholar.fetch_neighbors_by_doi` on them. That list replaces the reference list and the existing flow continues unchanged: `rank_neighbors`, the `STUB_CAP_PER_LIST` cap, `fetch_details` for the selected ids, and everything fetched before `_explore/` is wiped. Citations are untouched.

`mailto` comes from `CROSSREF_MAILTO` (environment or `.env`, loaded the way the CLI loads `S2_API_KEY`); when unset pass `""` (ticket 08 then sends no `mailto`). `_focus.md` gets one extra line directly under `## References`:

- fallback used: `references from Crossref (hidden on Semantic Scholar): <found> of <total> DOIs found`, where `<total>` is the number of Crossref reference DOIs and `<found>` the number of neighbors returned;
- Crossref has no record (`None`) or no reference DOIs, or the focus note has no `doi`: `references unavailable: hidden on Semantic Scholar and not on Crossref`, with zero reference stubs, citation stubs still written, exit 0.

Tests: temporary vault with a real saved note carrying a `doi`; fake transport routing by URL: `/references` replays `s2_references_elided.json`, `/citations` replays `s2_citations_page1.json`, Crossref replays `crossref_work.json`, and the batch-by-DOI POST answers with `s2_batch_by_doi.json` entries replicated under one new id per requested DOI (the shape stays real).

## Acceptance criteria

- [ ] Fallback path: `_explore/` holds one reference stub per Crossref reference DOI (count computed in the test from `crossref_work.json`'s `reference[].DOI`) plus the citation stubs from `s2_citations_page1.json`; `_focus.md` contains `references from Crossref (hidden on Semantic Scholar): N of N DOIs found` with N computed the same way.
- [ ] The batch-by-DOI POST bodies together contain exactly the `DOI:`-prefixed normalized reference DOIs from `crossref_work.json` (entries without a DOI absent); the Crossref request carries the test `mailto`, and with `CROSSREF_MAILTO` unset the Crossref URL contains no `mailto=`.
- [ ] No fallback when references are visible: replaying `s2_references_page1.json` / `s2_references_last.json` makes no Crossref request and no batch-by-DOI request (assert on the URLs the fake transport recorded), and `_focus.md` has no `from Crossref` line.
- [ ] Crossref 404: exit 0, `_focus.md` contains `references unavailable: hidden on Semantic Scholar and not on Crossref`, zero reference stubs, citation stubs written.
- [ ] Failure safety: a `ClientError` from the Crossref call or from the batch-by-DOI call makes `run_explore` return a failed summary and `main` exit 1, and every file in `_explore/` is byte-identical to before (snapshot as ticket 16's failure test does).

## Gate

```
ruff check .
python scripts/check_tests_first.py
pytest -q
```

CI (`.github/workflows/tests.yml`) runs exactly these, with `PYTHONUTF8=1` and bogus `OPENALEX_API_KEY` / `S2_API_KEY`. Zero failures before pushing.

## Comments
