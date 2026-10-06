# 13: Explore domain: neighbor model, ranking and stub filenames

**Status:** in-progress

**Runner:** any

**Auto-merge:** yes

**Blocked by:** 01, 04

**Spec:** `CONTEXT.md` (repo root; there is no separate `spec.md`)
**Binding:** `docs/adr/0001-tests-first.md`; `CONTEXT.md` (the design); `AGENTS.md` sections 2-3 (layers, invariants, testing)

## What to build

Create `src/lit_vault_tools/domain/neighbors.py` and add `STUB_TITLE_MAX_CHARS = 40` to `config.py`. Pure functions.

`Neighbor(s2_id, doi, title, authors, year, venue, citation_count, is_influential, tldr, abstract, relation)` is a frozen dataclass where `relation` is `"reference"` or `"citation"`; the lean list fetch fills only id, title, year, citation count, influential and DOI. `rank_neighbors(neighbors) -> list[Neighbor]` and `stub_filename(neighbor, taken) -> str`.

## Acceptance criteria

- [ ] `rank_neighbors` orders influential first, then by `citation_count` descending, then by `s2_id` ascending as the deterministic tie-break; `citation_count=None` ranks as 0; the input list is not mutated; the same input in any order gives the same output.
- [ ] `stub_filename` returns `"Jones 2019 - Dislocation loops in irradiated…"`-style names: first author's last word, year (or `n.d.`), ` - `, then the title cut to `STUB_TITLE_MAX_CHARS` characters (right-trimmed) plus `…` only when it was cut; a title of 40 characters or fewer has no ellipsis. A neighbor with no authors uses `Unknown`.
- [ ] Forbidden characters are replaced by `domain.people.sanitize_filename` (call it, do not copy it): a title containing `A/B: C?` yields a name with no `/`, `:` or `?`.
- [ ] Collisions: when the produced name is in `taken` (compared case-insensitively, as on Windows) a ` (2)` suffix is added, then ` (3)`; the returned name is never in `taken`, and the function does not mutate `taken`.

## Gate

```
ruff check .
python scripts/check_tests_first.py
pytest -q
```

CI (`.github/workflows/tests.yml`) runs exactly these, with `PYTHONUTF8=1` and bogus `OPENALEX_API_KEY` / `S2_API_KEY`. Zero failures before pushing.

## Comments
