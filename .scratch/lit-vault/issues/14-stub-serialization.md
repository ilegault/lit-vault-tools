# 14: Explore domain: stub note text and stub id reading

**Status:** in-progress

**Runner:** any

**Auto-merge:** yes

**Blocked by:** 02, 13

**Spec:** `CONTEXT.md` (repo root; there is no separate `spec.md`)
**Binding:** `docs/adr/0001-tests-first.md`; `CONTEXT.md` (the design); `AGENTS.md` sections 2-3 (layers, invariants, testing)

## What to build

Create `src/lit_vault_tools/domain/stubs.py`: `render_stub(neighbor) -> str` and `read_stub_ids(text) -> PaperIds`. Content per `CONTEXT.md` "Stub lifecycle" item 2.

Frontmatter: `type: stub`, `s2_id`, `doi` (normalized; omitted when unknown), `relation`. Body: `# <title>`, then authors (plain text, comma-separated), year, venue, citation count, influential yes/no, TL;DR, abstract, DOI link. Pure; tests build `Neighbor` values directly (our own type, not an API shape).

## Acceptance criteria

- [ ] For a fully populated neighbor, the rendered text equals a literal expected string written in the test (frontmatter block, title heading, authors line, year, venue, citation count, influential flag, tldr, abstract, DOI).
- [ ] Authors are plain text: the output contains no `[[` anywhere, even if an author name or title contains brackets (they are rendered as-is, not as links).
- [ ] A neighbor without `abstract`, `tldr` or `venue` renders without those sections and the text never contains the strings `None` or `null`; a neighbor without a DOI has no `doi:` line.
- [ ] `read_stub_ids(render_stub(n))` returns `PaperIds` with the neighbor's normalized DOI and `s2_id`; `render_stub` is deterministic (two calls give identical text).

## Gate

```
ruff check .
python scripts/check_tests_first.py
pytest -q
```

CI (`.github/workflows/tests.yml`) runs exactly these, with `PYTHONUTF8=1` and bogus `OPENALEX_API_KEY` / `S2_API_KEY`. Zero failures before pushing.

## Comments
