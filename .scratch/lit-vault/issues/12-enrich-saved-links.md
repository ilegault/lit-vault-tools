# 12: Enrich: refs and cited_by between saved papers

**Status:** done

**Runner:** any

**Auto-merge:** yes

**Blocked by:** 09

**Spec:** `CONTEXT.md` (repo root; there is no separate `spec.md`)
**Binding:** `docs/adr/0001-tests-first.md`; `CONTEXT.md` (the design); `AGENTS.md` sections 2-3 (layers, invariants, testing)

## What to build

Extend `src/lit_vault_tools/commands/enrich.py` (and a pure helper in `domain/`) so that after the per-note work, `refs` and `cited_by` are written. `refs` of paper A are the saved notes that A references, matched with `domain.doi.find_paper` against `PaperRecord.references` (OpenAlex ids) and `reference_dois`. Links are `[[<note filename stem>]]`, sorted by stem. `cited_by` is computed from the vault with no network: `cited_by(B)` is every saved note whose `refs` (after this run's update) link to B. Only saved papers ever appear.

Tests: temporary vault with several real `type: paper` notes; fake transport replaying `openalex_work.json` with its `referenced_works` rewritten to point at ids of the other test notes (the response shape stays real).

## Acceptance criteria

- [x] Saved A references saved B: after enrich, A's `refs` is exactly `["[[<B stem>]]"]` and B's `cited_by` is exactly `["[[<A stem>]]"]`; B's `enriched_on` is the run's `today` because its value changed.
- [x] References to papers that are not saved never appear: A references B plus an unsaved id, and `refs` still lists only B.
- [x] Matching by DOI works too: a Crossref-style record whose `reference_dois` contains B's DOI (differing only in case or URL prefix) links A to B.
- [x] Running enrich on A alone still updates B's `cited_by`, and re-running changes no file (bytes and mtimes).
- [x] Stale links are removed: after B's note is deleted from the vault, the next enrich drops B from A's `refs` and bumps A's `enriched_on`; the link list ordering is by stem, so file order never changes the output.

## Gate

```
ruff check .
python scripts/check_tests_first.py
pytest -q
```

CI (`.github/workflows/tests.yml`) runs exactly these, with `PYTHONUTF8=1` and bogus `OPENALEX_API_KEY` / `S2_API_KEY`. Zero failures before pushing.

## Comments

2026-10-06: Added `domain/links.py` (resolve_refs, cited_by_map, link helpers) and a second phase in `commands/enrich.py`: `refs` for notes fetched this run, then `cited_by` recomputed vault-wide from all `refs` (no network, written only on change, never creates an empty `cited_by`). Criteria 1, 2, 4, 5 covered by `tests/test_enrich_links.py` end to end; criterion 3 (DOI match in any case/prefix) by the `resolve_refs` unit test, since OpenAlex records carry no reference DOIs yet (ticket 11 supplies Crossref ones). Mutation checks: skipping the cited_by write and allowing self-links each turn tests red.
