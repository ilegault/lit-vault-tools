# 18: Explore: --more adds the next 200 without wiping

**Status:** ready-for-agent

**Runner:** any

**Auto-merge:** yes

**Blocked by:** 16

**Spec:** `CONTEXT.md` (repo root; there is no separate `spec.md`)
**Binding:** `docs/adr/0001-tests-first.md`; `CONTEXT.md` (the design); `AGENTS.md` sections 2-3 (layers, invariants, testing)

## What to build

Extend `run_explore` and the CLI with `--more` (`lit-vault explore --vault DIR NOTE --more`). It re-fetches and re-ranks the same focus, then writes the next `STUB_CAP_PER_LIST` ranked neighbors per list whose `s2_id` is not already present as a stub in `_explore/`, and rewrites `_focus.md` with the longer lists and counts. It never wipes and never rewrites an existing stub or `_trail.md`.

`--more` on a note that is not the current focus (per `_focus.md`'s `focus:` line) exits 1 with a message and changes nothing.

Tests: temporary vault; fake S2 transport with replicated lists of 450 references and 3 citations.

## Acceptance criteria

- [ ] After `explore` then `explore --more`, `_explore/` holds 400 reference stubs (the ranked top 400, no duplicates) and the same 3 citation stubs; `_focus.md` says `showing 400 of 450 references` and lists all 400 in rank order.
- [ ] Every stub file that existed before `--more` is byte-identical afterwards (compare hashes), and `_trail.md` is byte-identical.
- [ ] A third `--more` writes the remaining 50 and says `showing 450 of 450 references`; a fourth writes nothing and changes no file bytes.
- [ ] `--more` for a note other than the current focus exits 1, prints a message, and leaves the vault tree identical.
- [ ] A failed fetch during `--more` (`ClientError`) leaves every existing file byte-identical and exits 1.

## Gate

```
ruff check .
python scripts/check_tests_first.py
pytest -q
```

CI (`.github/workflows/tests.yml`) runs exactly these, with `PYTHONUTF8=1` and bogus `OPENALEX_API_KEY` / `S2_API_KEY`. Zero failures before pushing.

## Comments
