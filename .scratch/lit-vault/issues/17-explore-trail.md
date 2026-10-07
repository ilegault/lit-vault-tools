# 17: Explore trail and stubs as focus

**Status:** done

**Runner:** any

**Auto-merge:** yes

**Blocked by:** 16

**Spec:** `CONTEXT.md` (repo root; there is no separate `spec.md`)
**Binding:** `docs/adr/0001-tests-first.md`; `CONTEXT.md` (the design); `AGENTS.md` sections 2-3 (layers, invariants, testing)

## What to build

Extend `src/lit_vault_tools/commands/explore.py` with the rabbit-hole trail (`CONTEXT.md` Stub lifecycle item 5). `_explore/_trail.md` lists the last `config.TRAIL_LENGTH` foci newest first as an ordered list of `[[stem]]` links; that list is the only state (parse it on the next run). `run_explore` takes `trail_length` defaulting to `config.TRAIL_LENGTH`.

A focus may be a saved note (resolved by `doi`) or a stub inside `_explore/` (resolved by its `s2_id` with `read_stub_ids`, paper ref `<s2_id>`). Trail foci that are stubs survive the wipe; only neighbors are cleared. A saved-paper focus links to the real note and never creates a stub.

Tests: temporary vault; fake S2 transport that returns different replicated neighbor lists per paper ref.

## Acceptance criteria

- [x] Exploring saved note A, then stub B (from A's results), then stub C, then stub D yields `_trail.md` listing D, C, B newest first as links, with A's real note untouched; with `trail_length=3` and four foci the fourth drops the oldest.
- [x] Dropping the oldest focus deletes it only if it is a stub inside `_explore/`: a stub focus pushed out of the trail is deleted from `_explore/`, a saved note pushed out is still on disk byte-identical.
- [x] Trail foci that are stubs survive each wipe (their file bytes unchanged) while the previous focus's other neighbor stubs are deleted.
- [x] Exploring a note already in the trail moves it to the front without a duplicate entry and re-fetches its neighbors (the fake transport records the request).
- [x] Exploring a stub path resolves the paper by its `s2_id` (the fake transport sees `/paper/<s2_id>/references`), and `_focus.md` `focus:` links to that stub's stem.

## Gate

```
ruff check .
python scripts/check_tests_first.py
pytest -q
```

CI (`.github/workflows/tests.yml`) runs exactly these, with `PYTHONUTF8=1` and bogus `OPENALEX_API_KEY` / `S2_API_KEY`. Zero failures before pushing.

## Comments

2026-10-06: Added the trail to `commands/explore.py` (`_explore/_trail.md`, `trail_length`, stub foci resolved by s2_id, trail stubs preserved by `wipe_explore(keep=...)`, a neighbour that is already a trail stub is linked not duplicated). All five criteria covered by `tests/test_explore_trail.py`. Existing ticket-16 tests were updated only to exclude the new `_trail.md` from their stub counts; what they assert about stubs is unchanged. Mutation checks: ignoring `keep`, and not de-duplicating a re-explored focus, each turn tests red.
