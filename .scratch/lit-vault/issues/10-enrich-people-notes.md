# 10: Enrich writes author, institution and subfield notes and links

**Status:** ready-for-agent

**Runner:** any

**Auto-merge:** yes

**Blocked by:** 04, 07, 09

**Spec:** `CONTEXT.md` (repo root; there is no separate `spec.md`)
**Binding:** `docs/adr/0001-tests-first.md`; `CONTEXT.md` (the design); `AGENTS.md` sections 2-3 (layers, invariants, testing)

## What to build

Extend `src/lit_vault_tools/commands/enrich.py`: for each enriched paper, write `institutions`, `authors` and `subfield` link lists into the saved note and create or update the matching notes in `Authors/`, `Institutions/` and `Subfields/` (add these folder names to `config.py`). Identity is the OpenAlex id in the target note's frontmatter, found by scanning those folders (a helper in `vault/notes.py`), never the filename.

Existing author / institution / subfield notes are changed only through `domain.frontmatter.apply_enrichment`-style key edits plus `domain.people.merge_aliases`; their body is never touched. Use `domain.people.assign_author_filenames`, `institution_location` and the `render_*` functions for new notes, and `clients.geo_cache.get_institution_geo` for coordinates.

Tests: temporary vault; fake transport replaying `openalex_work.json` and `openalex_institution.json`; `LIT_VAULT_CACHE_DIR` set to `tmp_path`.

## Acceptance criteria

- [ ] After enrich, the saved note has `authors`, `institutions` and `subfield` as `[[...]]` link lists matching the fixture, and `Authors/`, `Institutions/`, `Subfields/` contain one note per fixture author / institution / subfield with the correct `openalex_id`, `type` and (authors) `aliases`.
- [ ] Re-running changes nothing: the whole vault tree (names and bytes) is identical, including `enriched_on` and the new notes.
- [ ] Collision: two papers whose authors share a display name but have different OpenAlex ids produce `Authors/Jane Doe.md` and `Authors/Jane Doe (<institution>).md`; running again with the papers in reverse order renames nothing.
- [ ] The developer's own work survives: an existing `Authors/<name>.md` containing typed body text keeps its body byte-for-byte while its `aliases` gains new name variants; and if that file is renamed by hand, the next enrich finds it by `openalex_id`, creates no duplicate, and the saved note links to the renamed file.
- [ ] Institution `location` comes from the fake geo lookup as `lat,lng`; when the lookup returns `None` the institution note has no `location:` line and no `0,0` appears in the file; the geo cache is read on the second run (the fake transport's institution call count does not grow).

## Gate

```
ruff check .
python scripts/check_tests_first.py
pytest -q
```

CI (`.github/workflows/tests.yml`) runs exactly these, with `PYTHONUTF8=1` and bogus `OPENALEX_API_KEY` / `S2_API_KEY`. Zero failures before pushing.

## Comments
