# 07: Cached institution coordinate lookup

**Status:** done

**Runner:** any

**Auto-merge:** yes

**Blocked by:** 06

**Spec:** `CONTEXT.md` (repo root; there is no separate `spec.md`)
**Binding:** `docs/adr/0001-tests-first.md`; `CONTEXT.md` (the design); `AGENTS.md` sections 2-3 (layers, invariants, testing)

## What to build

Add `fetch_institution_geo(institution_id, api_key, transport) -> tuple[float, float] | None` to `src/lit_vault_tools/clients/openalex.py` and create `src/lit_vault_tools/clients/geo_cache.py` with `get_institution_geo(institution_id, fetch, cache_dir)`.

Cache location per `CONTEXT.md` decision 13: `LIT_VAULT_CACHE_DIR` if set, else `%LOCALAPPDATA%/lit-vault-tools`, else `$XDG_CACHE_HOME/lit-vault-tools`, else `~/.cache/lit-vault-tools`; file `institutions.json`. The cache lives outside the vault. It sits in `clients/` because it only caches a client's responses.

Tests fake the transport with `tests/fixtures/openalex_institution.json` and point `LIT_VAULT_CACHE_DIR` at `tmp_path`; the JSON file read and write is real.

## Acceptance criteria

- [x] `fetch_institution_geo` returns the `(lat, lng)` found in the fixture (read the fixture for the field path) and `None` when the fixture's coordinates are null (use a copy of the fixture with them nulled).
- [x] `get_institution_geo` on a cold cache calls `fetch` once and writes `institutions.json` under the cache dir; a second call for the same id returns the same value and the fake transport's call count stays 1.
- [x] A `None` result is not cached: calling twice for an unknown location calls `fetch` twice (so it can be found later).
- [x] A corrupted `institutions.json` (invalid JSON) is treated as an empty cache and rewritten valid; no exception escapes.
- [x] Cache directory resolution is tested for each branch (`LIT_VAULT_CACHE_DIR`, `LOCALAPPDATA`, `XDG_CACHE_HOME`, home fallback) by monkeypatching environment variables; nothing is ever written inside a vault directory or the repo (assert the temp vault listing is unchanged).

## Gate

```
ruff check .
python scripts/check_tests_first.py
pytest -q
```

CI (`.github/workflows/tests.yml`) runs exactly these, with `PYTHONUTF8=1` and bogus `OPENALEX_API_KEY` / `S2_API_KEY`. Zero failures before pushing.

## Comments

2026-10-06: Added `fetch_institution_geo` (openalex.py) and `clients/geo_cache.py` (cache dir resolution, JSON cache, None never cached, corrupt cache rewritten). All five criteria covered by `tests/test_geo_cache.py`. Mutation check: caching None turns two tests red.
