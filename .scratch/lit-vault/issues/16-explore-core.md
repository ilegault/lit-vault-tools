# 16: lit-vault explore: stubs and _focus.md for one focus paper

**Status:** done

**Runner:** any

**Auto-merge:** yes

**Blocked by:** 03, 14, 15

**Spec:** `CONTEXT.md` (repo root; there is no separate `spec.md`)
**Binding:** `docs/adr/0001-tests-first.md`; `CONTEXT.md` (the design); `AGENTS.md` sections 2-3 (layers, invariants, testing)

## What to build

Create `src/lit_vault_tools/commands/explore.py` with `run_explore(vault, focus_note, api_key, transport, sleep, clock) -> ExploreSummary`, add the `explore` subcommand to `cli.py` (`lit-vault explore --vault DIR NOTE`; `S2_API_KEY` from the environment or `.env`, as `enrich` loads its key), and add a vault helper `vault/explore_dir.py` (`wipe_explore`, `write_stub`).

Flow: read the focus note's `doi` -> fetch lean neighbors for both relations -> `domain.neighbors.rank_neighbors` -> take the top `STUB_CAP_PER_LIST` of each list -> `fetch_details` for just those -> **only then** wipe `_explore/` and write one stub per neighbor (`stub_filename`, `render_stub`) plus `_explore/_focus.md`. `_focus.md` has `type: focus`, a `focus: [[<focus note stem>]]` line, `## References` and `## Citations` link lists (`[[<stub name>]]`, in rank order) and a line `showing 200 of 3,412 citations` per list. Saved notes are never modified.

Tests: temporary vault with real notes; fake transport replaying the S2 fixtures; neighbor lists are built by replicating fixture items under new ids.

## Acceptance criteria

- [x] With 450 references and 3 citations upstream, `_explore/` holds exactly 200 reference stubs and 3 citation stubs plus `_focus.md`; the stubs are the 200 highest by `rank_neighbors`; `_focus.md` lists them in rank order and contains `showing 200 of 450 references` and `showing 3 of 3 citations`.
- [x] Each stub file's text equals `render_stub` of its neighbor merged with the details from the batch response; the batch POSTs together contain only the ids of the 203 selected neighbors, not all 453.
- [x] `_explore/` is wiped before writing: a pre-existing `_explore/old stub.md` is gone afterwards; every note outside `_explore/` is byte-identical (snapshot the vault tree before and after, including the focus note); `_explore/` is created when missing.
- [x] Failure leaves the vault alone: when the fake transport raises `ClientError` on the second page request, `run_explore` returns a failed summary, `main` exits 1, and `_explore/` still holds its previous files byte-for-byte (the wipe never ran).
- [x] A focus note without a `doi` exits 1 with a message and changes nothing; a missing `S2_API_KEY` exits 2 with no transport call.

## Gate

```
ruff check .
python scripts/check_tests_first.py
pytest -q
```

CI (`.github/workflows/tests.yml`) runs exactly these, with `PYTHONUTF8=1` and bogus `OPENALEX_API_KEY` / `S2_API_KEY`. Zero failures before pushing.

## Comments

2026-10-06: Added `commands/explore.py` (run_explore, ExploreSummary), `vault/explore_dir.py` (wipe_explore, write_stub) and the `explore` subcommand (cli.py now dispatches per command; explore needs S2_API_KEY, exit 2 if missing, exit 1 on failure). Everything is fetched before the wipe. Details are fetched only for the selected stubs. `_focus.md` frontmatter writes `focus: "[[stem]]"` quoted so Obsidian reads it as a link property. Known gaps left to later tickets: a focus note that lives inside `_explore/` is wiped with it (17, trail); hidden references are reported as hidden, not fetched from Crossref (22). All five criteria covered by `tests/test_explore.py` and `tests/test_explore_dir.py`. Mutation checks: wiping before fetching, and requesting details for all neighbours, each turn tests red.
