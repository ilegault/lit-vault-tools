# 08: Crossref and OSTI fallback clients

**Status:** ready-for-agent

**Runner:** any

**Auto-merge:** yes

**Blocked by:** 05, 06

**Spec:** `CONTEXT.md` (repo root; there is no separate `spec.md`)
**Binding:** `docs/adr/0001-tests-first.md`; `CONTEXT.md` (the design); `AGENTS.md` sections 2-3 (layers, invariants, testing)

## What to build

Create `src/lit_vault_tools/clients/crossref.py` and `src/lit_vault_tools/clients/osti.py`, both returning the same `PaperRecord` as `clients/openalex.py` (`domain/paper_record.py`).

`crossref.fetch_work(doi, mailto, transport) -> PaperRecord | None` returns a record with `openalex_id=None`, empty `authors` / `institutions` / `countries`, `subfield=None`, empty `references`, and `reference_dois` from the work's `reference[].DOI` (normalized, entries without a DOI skipped). `osti.fetch_by_title(title, transport) -> PaperRecord | None` returns a record with the report's `doi` when present, otherwise `doi=None`, and the same empty fields. The `mailto` goes where the Crossref polite pool expects it, recorded in `tests/fixtures/README.md`.

Tests fake only the transport, replaying `crossref_work.json` and `osti_record.json`.

## Acceptance criteria

- [ ] `crossref.fetch_work` with the fixture returns `reference_dois` equal to the fixture's `reference[].DOI` values, normalized, in order, excluding entries that lack a DOI, and `doi` equal to the normalized fixture DOI.
- [ ] `crossref.fetch_work` sends the `mailto` exactly where `tests/fixtures/README.md` records it; a 404 returns `None`; 429/500 raise `ClientError`.
- [ ] `osti.fetch_by_title` with the fixture returns a record whose `doi` equals the fixture's DOI normalized (or `None` when the fixture has none), and returns `None` when the transport returns an empty result list (use a copy of the fixture with the list emptied).
- [ ] `crossref.fetch_work` with `mailto=""` sends no `mailto` parameter at all (the test asserts the requested URL contains no `mailto=`), so Explore can call it when `CROSSREF_MAILTO` is unset.
- [ ] Neither client's `ClientError` message nor any log record contains the `mailto` value used in the test.

## Gate

```
ruff check .
python scripts/check_tests_first.py
pytest -q
```

CI (`.github/workflows/tests.yml`) runs exactly these, with `PYTHONUTF8=1` and bogus `OPENALEX_API_KEY` / `S2_API_KEY`. Zero failures before pushing.

## Comments
