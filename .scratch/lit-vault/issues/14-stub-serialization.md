# 14: Explore domain: stub note text and stub id reading

**Status:** done

**Runner:** any

**Auto-merge:** yes

**Blocked by:** 02, 13

**Spec:** `CONTEXT.md` (repo root; there is no separate `spec.md`)
**Binding:** `docs/adr/0001-tests-first.md`; `CONTEXT.md` (the design); `AGENTS.md` sections 2-3 (layers, invariants, testing)

## What to build

Create `src/lit_vault_tools/domain/stubs.py`: `render_stub(neighbor) -> str` and `read_stub_ids(text) -> PaperIds`. Content per `CONTEXT.md` "Stub lifecycle" item 2.

Frontmatter: `type: stub`, `s2_id`, `doi` (normalized; omitted when unknown), `relation`. Body: `# <title>`, then authors (plain text, comma-separated), year, venue, citation count, influential yes/no, TL;DR, abstract, DOI link. Pure; tests build `Neighbor` values directly (our own type, not an API shape).

## Acceptance criteria

- [x] For a fully populated neighbor, the rendered text equals a literal expected string written in the test (frontmatter block, title heading, authors line, year, venue, citation count, influential flag, tldr, abstract, DOI).
- [x] Authors are plain text: the output contains no `[[` anywhere, even if an author name or title contains brackets (they are rendered as-is, not as links).
- [x] A neighbor without `abstract`, `tldr` or `venue` renders without those sections and the text never contains the strings `None` or `null`; a neighbor without a DOI has no `doi:` line.
- [x] `read_stub_ids(render_stub(n))` returns `PaperIds` with the neighbor's normalized DOI and `s2_id`; `render_stub` is deterministic (two calls give identical text).

## Gate

```
ruff check .
python scripts/check_tests_first.py
pytest -q
```

CI (`.github/workflows/tests.yml`) runs exactly these, with `PYTHONUTF8=1` and bogus `OPENALEX_API_KEY` / `S2_API_KEY`. Zero failures before pushing.

## Comments

2026-10-06: added `domain/stubs.py` (`render_stub`, `read_stub_ids`). `tests/test_stubs.py` covers criterion 1 (literal expected text), 2 (no `[[` even with brackets in author/title/abstract; they are broken apart as `[ [` since a literal `[[` would be a link), 3 (omitted sections, no None/null, no `doi:` line), 4 (id round trip, determinism). Mutation check: disabling bracket defusing turns the wikilink test red.
