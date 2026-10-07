# 20: Capture the Semantic Scholar batch-by-DOI fixture

**Status:** ready-for-developer

**Runner:** developer

**Auto-merge:** no

**Blocked by:** None (can start immediately)

**Spec:** `CONTEXT.md` (repo root; there is no separate `spec.md`)
**Binding:** `CONTEXT.md` decisions 15 and 17; `AGENTS.md` section 3 (fixtures are real)

## What to build

A person must do this: it needs the live `S2_API_KEY` and network, which an agent must never use (`AGENTS.md` protocol rule 10). Ticket 21 parses this response and may not guess its shape.

From the repo root in PowerShell, with the key loaded from `.env`:

```powershell
$key = ((Get-Content .env | Select-String '^S2_API_KEY=').Line -split '=',2)[1].Trim()
'{"ids":["DOI:10.1016/j.actamat.2012.11.004","DOI:10.2172/911784","DOI:10.3390/app9173486","DOI:10.0000/not-a-real-doi"]}' | Set-Content -Encoding ascii -NoNewline body.json
curl.exe -s -X POST -H "x-api-key: $key" -H "Content-Type: application/json" --data-binary "@body.json" -o tests/fixtures/s2_batch_by_doi.json "https://api.semanticscholar.org/graph/v1/paper/batch?fields=title,year,citationCount,externalIds"
Remove-Item body.json
Get-Content tests/fixtures/s2_batch_by_doi.json
```

The first three DOIs are real entries from `crossref_work.json`'s `reference` list; the last is deliberately fake so the response contains a real `null`. If the output is a `429` message instead of a JSON list, wait a minute and run the `curl.exe` line again.

Then append an entry for `s2_batch_by_doi.json` to `tests/fixtures/README.md` in the same format as the others: method `POST`, the URL, header `x-api-key: <KEY>` plus `Content-Type: application/json`, the body JSON above, and the capture date.

## Acceptance criteria

- [ ] `tests/fixtures/s2_batch_by_doi.json` parses as a JSON list of exactly 4 entries, in request order; the last (fake DOI) entry is `null`; at least two entries are objects with `paperId`, `title` and `externalIds.DOI`.
- [ ] The README entry records method, URL, headers (key as `<KEY>`), body and capture date.
- [ ] Neither the fixture nor the README contains the key value (search for it).
- [ ] Set this ticket `Status: done` after committing the fixture on a branch and opening a PR.

## Gate

```
ruff check .
python scripts/check_tests_first.py
pytest -q
```

CI (`.github/workflows/tests.yml`) runs exactly these, with `PYTHONUTF8=1` and bogus `OPENALEX_API_KEY` / `S2_API_KEY`. Zero failures before pushing.

## Comments
