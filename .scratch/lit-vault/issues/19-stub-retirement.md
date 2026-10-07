# 19: Stub retirement when a paper is saved

**Status:** done

**Runner:** any

**Auto-merge:** yes

**Blocked by:** 09, 16

**Spec:** `CONTEXT.md` (repo root; there is no separate `spec.md`)
**Binding:** `docs/adr/0001-tests-first.md`; `CONTEXT.md` (the design); `AGENTS.md` sections 2-3 (layers, invariants, testing)

## What to build

Create `src/lit_vault_tools/vault/retire.py` with `retire_stubs(vault) -> list[str]`, called at the end of both `commands.enrich.run_enrich` and `commands.explore.run_explore`.

For each `type: stub` note directly under `_explore/`, if its `read_stub_ids` match a saved paper from `scan_saved_notes` (`domain.doi.find_paper`: DOI, or `s2_id`), delete the stub and rewrite `[[<stub stem>]]` to `[[<saved note stem>]]` in `_explore/_focus.md` and `_explore/_trail.md`. Deletion happens **only** inside `_explore/` (invariant 2).

Tests: temporary vault; real files; transports fake where the commands need them.

## Acceptance criteria

- [x] A stub whose DOI matches a saved note (differing only by case / URL prefix) is deleted, and `[[Stub stem]]` in `_focus.md` and `_trail.md` now reads `[[<saved stem>]]`; the saved note and every other `_explore/` file are byte-identical.
- [x] A stub with no match stays; a stub with no `doi` but an `s2_id` equal to a saved note's `s2_id` is retired.
- [x] Never outside `_explore/`: a `type: stub` note at `Papers/x.md` whose DOI matches a saved paper still exists byte-identical afterwards; and no saved paper note is ever deleted (assert the set of saved note paths is unchanged).
- [x] Via `explore`: when one of the fetched neighbors has a saved paper's DOI, after the run no stub exists for it and `_focus.md` links to the saved note instead.
- [x] Via `enrich`: with a stub in `_explore/` and a newly added saved note with the same DOI, `run_enrich` deletes the stub and repoints the links; running `retire_stubs` again changes no file (bytes and mtimes).

## Gate

```
ruff check .
python scripts/check_tests_first.py
pytest -q
```

CI (`.github/workflows/tests.yml`) runs exactly these, with `PYTHONUTF8=1` and bogus `OPENALEX_API_KEY` / `S2_API_KEY`. Zero failures before pushing.

## Comments

2026-10-06: Added `vault/retire.py` (`retire_stubs`), called at the end of `run_enrich` and `run_explore`. Matches by DOI or s2_id via `find_paper`; deletes only `type: stub` notes directly under `_explore/`; repoints links in `_focus.md` and `_trail.md` and drops a trail entry that would now repeat. All five criteria covered by `tests/test_retire.py`. One existing test changed: `tests/test_enrich.py::test_only_paper_notes_are_processed` had an `_explore/` stub carrying the same DOI as a saved paper, which retirement now deletes by design; the stub now has an unrelated DOI so the test still asserts that enrich does not process stubs. My own new tests first used `10.1/same`, which `normalize_doi` rejects, so they were passing trivially; fixed to valid DOIs before landing. Known quirk, not fixed here: `explore --more` re-selects a retired neighbour as a new one each time (it has no stub), so each load-more yields slightly fewer than 200 new stubs when many neighbours are saved. Mutation checks: no repointing, recursing past `_explore/`, and DOI-only matching each turn tests red.
