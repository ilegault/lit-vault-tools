# 02: Frontmatter regions: byte-preserving read and enrichment write

**Status:** done

**Runner:** any

**Auto-merge:** yes

**Blocked by:** 01

**Spec:** `CONTEXT.md` (repo root; there is no separate `spec.md`)
**Binding:** `docs/adr/0001-tests-first.md`; `CONTEXT.md` (the design); `AGENTS.md` sections 2-3 (layers, invariants, testing)

## What to build

Create `src/lit_vault_tools/domain/frontmatter.py`. Frontmatter is parsed line-wise, **not** with a YAML library (the project adds no runtime dependency): everything that is not an enrichment-owned line is carried through verbatim.

API: `split_note(text) -> NoteParts` (with `.render()`), `read_scalar(parts, key)`, `read_list(parts, key)`, `apply_enrichment(parts, values, today) -> NoteParts`. Use `config.ENRICHMENT_KEYS`. Pure functions; tests build note strings by hand (they are our own file format, not an API response) and need no files.

## Acceptance criteria

- [x] `split_note(text).render() == text` for: a normal note, a note with no frontmatter, a note with an empty body, a body containing its own `---` lines, and a CRLF note (assert the CRLF bytes survive). The body of a note is returned byte-for-byte.
- [x] `read_scalar` returns the value for `doi: 10.1016/x`, `doi: "10.1016/x"` and `doi: 10.1016/x  # note` (quotes and trailing comment stripped), and `None` for an absent key. `read_list` returns `["[[A]]", "[[B]]"]` for `refs: ["[[A]]", "[[B]]"]` and `[]` for `refs: []`.
- [x] `apply_enrichment` with values for several keys leaves every non-enrichment line (including multi-line Zotero values such as `abstract: |` blocks) identical and in the same order, writes the owned keys in `ENRICHMENT_KEYS` order after the marker line `# ---- enrichment-script-owned ----`, serializes lists as `["[[X]]", ...]`, and omits a key whose value is `None`. The body is identical.
- [x] `apply_enrichment` raises `ValueError` for a key not in `ENRICHMENT_KEYS` (`citekey`, `title`, `doi`), and the input `NoteParts` is unchanged. Applying the same values twice gives text identical to applying them once.
- [x] `enriched_on` rule: with no existing block it is set to `today`; with an existing block and identical values (ignoring `enriched_on`) the existing date is kept even when `today` differs; when any other owned value changed, `enriched_on` becomes `today`. New lines use the note's own line ending (a CRLF note stays all-CRLF).

## Gate

```
ruff check .
python scripts/check_tests_first.py
pytest -q
```

CI (`.github/workflows/tests.yml`) runs exactly these, with `PYTHONUTF8=1` and bogus `OPENALEX_API_KEY` / `S2_API_KEY`. Zero failures before pushing.

## Comments

Done (2026-10-06): added `domain/frontmatter.py` and `tests/test_frontmatter.py`.
Criterion 1 (round trips, CRLF, body) and 2 (read_scalar/read_list) and 3-5 (apply_enrichment, ValueError, enriched_on, CRLF) are all covered there.
Design decisions beyond the ticket, documented in the module docstring: `values` is a patch (None removes a key, unmentioned keys are kept); passing `enriched_on` raises ValueError; a no-op apply returns the note unchanged (so hand-formatted owned lines survive a clean re-run); a note with no frontmatter gets a block holding only the enrichment keys.
Mutation checks (each turned tests red): skipping block continuation lines, writing `\n` instead of the note's eol, never bumping `enriched_on`, and returning early on no change.
