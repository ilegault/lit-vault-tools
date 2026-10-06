# 01: DOI normalization, paper matching and config constants

**Status:** done

**Runner:** any

**Auto-merge:** yes

**Blocked by:** None (can start immediately)

**Spec:** `CONTEXT.md` (repo root; there is no separate `spec.md`)
**Binding:** `docs/adr/0001-tests-first.md`; `CONTEXT.md` (the design); `AGENTS.md` sections 2-3 (layers, invariants, testing)

## What to build

Create `src/lit_vault_tools/config.py` (constants only, no I/O) and `src/lit_vault_tools/domain/doi.py` (new package `domain/`, with `__init__.py`).

`config.py` exports `ENRICHMENT_KEYS`, `EXPLORE_DIR`, `STUB_CAP_PER_LIST`, `TRAIL_LENGTH`. `domain/doi.py` exports `normalize_doi(raw)`, a frozen dataclass `PaperIds(doi, openalex_id, s2_id)` (all default `None`), and `find_paper(ids, candidates)`.

Pure functions; the tests need no fakes and no files.

## Acceptance criteria

- [x] `normalize_doi` maps each of `"https://doi.org/10.1016/J.JNUCMAT.2021.000000"`, `"http://dx.doi.org/10.1016/J.JNUCMAT.2021.000000"`, `"doi:10.1016/J.JNUCMAT.2021.000000"` and `" 10.1016/j.jnucmat.2021.000000 "` to exactly `"10.1016/j.jnucmat.2021.000000"` (parametrized test).
- [x] `normalize_doi` returns `None` for `None`, `""`, `"   "` and `"not a doi"`; and `normalize_doi(normalize_doi(x)) == normalize_doi(x)` for every valid case above.
- [x] `find_paper(ids, candidates)` returns the index of the first candidate sharing any non-`None` id with `ids`: a test where the DOIs differ only by case and URL prefix returns that candidate's index, and a test where only `openalex_id` or only `s2_id` matches also returns it.
- [x] `find_paper` returns `None` when nothing matches, and returns `None` when `ids` is all-`None` even if a candidate is all-`None` (a missing id never equals a missing id). The function takes no filename argument, so it cannot match on one.
- [x] `config.ENRICHMENT_KEYS == ("openalex_id", "s2_id", "oa_status", "institutions", "countries", "authors", "subfield", "refs", "cited_by", "enrich_status", "enriched_on")` (the owned keys in `CONTEXT.md`'s frontmatter block), `EXPLORE_DIR == "_explore"`, `STUB_CAP_PER_LIST == 200`, `TRAIL_LENGTH == 3`.

## Gate

```
ruff check .
python scripts/check_tests_first.py
pytest -q
```

CI (`.github/workflows/tests.yml`) runs exactly these, with `PYTHONUTF8=1` and bogus `OPENALEX_API_KEY` / `S2_API_KEY`. Zero failures before pushing.

## Comments

Done (2026-10-06): added `config.py`, `domain/doi.py`, `tests/test_config.py`, `tests/test_doi.py`.
Criteria 1-3 (normalize, idempotence, find_paper matching) and 4 (no-match, all-None) are covered by `tests/test_doi.py`; criterion 5 by `tests/test_config.py`. Mutation check: removing `.lower()` from `normalize_doi` turned the case-insensitivity tests red. No bench verification needed.
