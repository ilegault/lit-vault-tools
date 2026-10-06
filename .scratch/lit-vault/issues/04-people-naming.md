# 04: Author, institution and subfield naming and rendering

**Status:** in-progress

**Runner:** any

**Auto-merge:** yes

**Blocked by:** 01

**Spec:** `CONTEXT.md` (repo root; there is no separate `spec.md`)
**Binding:** `docs/adr/0001-tests-first.md`; `CONTEXT.md` (the design); `AGENTS.md` sections 2-3 (layers, invariants, testing)

## What to build

Create `src/lit_vault_tools/domain/people.py`. Pure functions; no files.

Dataclasses `AuthorRef(openalex_id, display_name)` and `InstitutionRef(openalex_id, display_name, ror, country, institution_type)` (fields beyond the ids may be `None`). Functions: `sanitize_filename`, `assign_author_filenames`, `merge_aliases`, `institution_location`, `render_author_note`, `render_institution_note`, `render_subfield_note`. Rules are in `CONTEXT.md` under "Authors" and decisions 15-16 (`type: institution`, `institution_type`).

## Acceptance criteria

- [ ] `sanitize_filename("A/B: C?")` replaces each of `\ / : * ? " < > |` with `-` and trims trailing dots and spaces (Windows-safe), e.g. `"A-B- C-"`; a name that sanitizes to empty becomes `"Unnamed"`.
- [ ] `assign_author_filenames(seen, existing)`: with two different `openalex_id`s both displayed `Jane Doe`, the second gets `Jane Doe (Oak Ridge National Laboratory)`; a still-colliding third gets ` (2)` appended. `existing` (id -> filename) is never changed: running again with the authors in reverse order returns the same filename for every id already in `existing`.
- [ ] `merge_aliases(existing, seen_names, display_name)` returns existing aliases in their order followed by new unseen variants in first-seen order, with no duplicates and without `display_name` itself; calling it twice gives the same list.
- [ ] `institution_location(lat, lng)` returns `"35.9,-84.3"`-style `"lat,lng"` text for known coordinates and `None` when either is `None` or both are `0` (never `"0,0"`). `render_institution_note` emits no `location:` line when it is `None` and the text contains no `0,0` anywhere.
- [ ] `render_author_note` returns text with `type: author`, `openalex_id: <id>`, `aliases: [...]` and an empty body; `render_institution_note` has `type: institution`, `ror`, `country`, `institution_type`, `openalex_id`; `render_subfield_note` has `type: subfield`. Output is deterministic (same input, identical text).

## Gate

```
ruff check .
python scripts/check_tests_first.py
pytest -q
```

CI (`.github/workflows/tests.yml`) runs exactly these, with `PYTHONUTF8=1` and bogus `OPENALEX_API_KEY` / `S2_API_KEY`. Zero failures before pushing.

## Comments
