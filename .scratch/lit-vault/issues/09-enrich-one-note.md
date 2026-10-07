# 09: lit-vault enrich: one note end to end (OpenAlex only)

**Status:** done

**Runner:** any

**Auto-merge:** yes

**Blocked by:** 02, 03, 06

**Spec:** `CONTEXT.md` (repo root; there is no separate `spec.md`)
**Binding:** `docs/adr/0001-tests-first.md`; `CONTEXT.md` (the design); `AGENTS.md` sections 2-3 (layers, invariants, testing)

## What to build

Create `src/lit_vault_tools/cli.py` (`main(argv)`, argument parsing and `.env` loading only), `src/lit_vault_tools/commands/__init__.py` and `src/lit_vault_tools/commands/enrich.py` with `run_enrich(vault, notes, api_key, transport, today) -> EnrichSummary`.

CLI: `lit-vault enrich --vault DIR [NOTE ...]`; with no `NOTE` it enriches every `type: paper` note from `vault.notes.scan_saved_notes`. `--vault` falls back to the `LIT_VAULT_DIR` environment variable. `OPENALEX_API_KEY` comes from the environment or a `.env` file in the current directory (`KEY=VALUE` lines; the environment wins).

This ticket writes only `openalex_id`, `oa_status`, `countries`, `enrich_status`, `enriched_on` via `domain.frontmatter.apply_enrichment`. Statuses: `ok`, `no_doi` (note has no `doi`), `not_found` (OpenAlex 404), `error` (`ClientError`; the note is left untouched and the run continues). Later tickets add authors, institutions, fallbacks and links.

Tests use a temporary vault with real note files and a fake transport replaying `tests/fixtures/openalex_work.json`.

## Acceptance criteria

- [x] Argument parsing: `build_parser().parse_args(["enrich", "--vault", "V", "a.md"])` yields vault `V` and notes `["a.md"]`. `main(["enrich", "--vault", "V"])` with no `OPENALEX_API_KEY` in the environment or `.env` returns exit code 2, prints a message to stderr, and makes no transport call. A `.env` file with `OPENALEX_API_KEY=x` supplies the key; an environment variable of the same name overrides the file.
- [x] `run_enrich` on a note with a `doi` leaves the note with `openalex_id`, `oa_status`, `countries` taken from the fixture and `enrich_status: ok`, `enriched_on: <today>`; every pre-existing line and the whole body are byte-identical (compare with `split_note`). Only `type: paper` notes are processed; an author note, a note under `_explore/` and a non-paper note are byte-identical afterwards.
- [x] Idempotent: running a second time with a later `today` and the same fixture leaves every file's bytes unchanged and the mtime unchanged (`write_note` returned `False`).
- [x] Upstream change: replaying a copy of the fixture with a different open-access status changes only the `oa_status` line and `enriched_on` (now the new `today`).
- [x] A note with no `doi` gets `enrich_status: no_doi`; a 404 gives `not_found`; a 500 gives `error` and the note's bytes are unchanged; in all three cases the other notes in the run are still enriched, the summary counts each status, and `main` returns exit code 1 when any note ended `error`, else 0.

## Gate

```
ruff check .
python scripts/check_tests_first.py
pytest -q
```

CI (`.github/workflows/tests.yml`) runs exactly these, with `PYTHONUTF8=1` and bogus `OPENALEX_API_KEY` / `S2_API_KEY`. Zero failures before pushing.

## Comments

2026-10-06: Added `cli.py` (parser, .env loading, exit codes 0/1/2), `commands/enrich.py` (`run_enrich`, `EnrichSummary`). All five criteria covered by `tests/test_enrich.py`. Explicit NOTE paths resolve against the cwd, else the vault. Mutation check: dropping the paper-only guard turns a test red. Not covered here: authors, institutions, fallbacks, links (later tickets).
