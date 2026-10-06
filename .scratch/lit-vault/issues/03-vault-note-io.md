# 03: Vault note scanning and safe writing

**Status:** ready-for-agent

**Runner:** any

**Auto-merge:** yes

**Blocked by:** 02

**Spec:** `CONTEXT.md` (repo root; there is no separate `spec.md`)
**Binding:** `docs/adr/0001-tests-first.md`; `CONTEXT.md` (the design); `AGENTS.md` sections 2-3 (layers, invariants, testing)

## What to build

Create `src/lit_vault_tools/vault/notes.py` (package `vault/`). It is the only code that reads or writes note files.

API: `scan_saved_notes(vault) -> list[SavedNote]` where `SavedNote` holds `path`, `text`, `ids: PaperIds` (DOI normalized with `domain.doi.normalize_doi`, `openalex_id`, `s2_id` read with `domain.frontmatter.read_scalar`); and `write_note(path, text) -> bool`.

Tests use a real temporary vault (`tmp_path`) with real `.md` files. Nothing is faked.

## Acceptance criteria

- [ ] `scan_saved_notes` returns exactly the notes whose frontmatter has `type: paper`, found recursively, in sorted path order; it ignores `type: author` / `type: stub` notes, anything under `_explore/`, anything under a dot-directory such as `.obsidian/`, and non-`.md` files. The returned `ids.doi` is normalized (a note with `doi: https://doi.org/10.1016/ABC` yields `10.1016/abc`).
- [ ] Files are read and written without newline translation: a CRLF note scanned and re-written with its own `text` is byte-identical on disk (compare bytes).
- [ ] `write_note(path, text)` returns `False` and does not touch the file (assert `st_mtime_ns` unchanged) when `text` equals the current content; it returns `True` and the bytes on disk equal `text` when it differs.
- [ ] The write is atomic and leaves no strays: after writing, the sorted directory listing of the vault equals the listing before (no temp files left), and a failure injected between the temp write and the replace (monkeypatch `os.replace` to raise) leaves the original file's bytes intact.
- [ ] Scanning every note and re-writing each with its own text leaves the vault's file names, count and bytes unchanged: nothing is renamed, moved or deleted.

## Gate

```
ruff check .
python scripts/check_tests_first.py
pytest -q
```

CI (`.github/workflows/tests.yml`) runs exactly these, with `PYTHONUTF8=1` and bogus `OPENALEX_API_KEY` / `S2_API_KEY`. Zero failures before pushing.

## Comments
