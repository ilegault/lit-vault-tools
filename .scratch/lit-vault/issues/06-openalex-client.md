# 06: OpenAlex client: one work by DOI as plain data

**Status:** ready-for-agent

**Runner:** any

**Auto-merge:** yes

**Blocked by:** 04, 05

**Spec:** `CONTEXT.md` (repo root; there is no separate `spec.md`)
**Binding:** `docs/adr/0001-tests-first.md`; `CONTEXT.md` (the design); `AGENTS.md` sections 2-3 (layers, invariants, testing)

## What to build

Create `src/lit_vault_tools/clients/http.py` (the `Transport` protocol and the stdlib default `stdlib_transport`, built on `http.client`, decision 12). Do **not** use `urllib`: it re-capitalises header names (`x-api-key` becomes `X-api-key`), and Semantic Scholar's key header is case-sensitive, so every request would silently go out unauthenticated, `src/lit_vault_tools/domain/paper_record.py` (`PaperRecord`) and `src/lit_vault_tools/clients/openalex.py`.

`Transport` is a callable `(method, url, headers, body) -> HttpResponse(status, body_bytes)`. `ClientError(status, url)` is raised for non-success statuses other than 404; its message must not contain the API key. `openalex.fetch_work(doi, api_key, transport) -> PaperRecord | None` (`None` on 404). `PaperRecord` carries: `openalex_id` (`W...`, the `https://openalex.org/` prefix stripped), normalized `doi`, `oa_status`, `authors` (list of `(AuthorRef, [institution display names])` from `domain/people.py`), `institutions` (list of `InstitutionRef`), `countries`, `subfield` (display name or `None`), `references` (list of `W...` ids) and `reference_dois` (default empty).

Build the request exactly as recorded in `tests/fixtures/README.md`. Tests fake **only** the transport, replaying `tests/fixtures/openalex_work.json`; the parsing is real. Read the fixture to learn the field paths; do not guess them.

## Acceptance criteria

- [ ] With the fixture replayed, `fetch_work` returns a `PaperRecord` whose `openalex_id` equals the fixture's `id` minus the URL prefix, whose `doi` equals `normalize_doi` of the fixture's `doi`, whose `oa_status` equals the fixture's open-access status, and whose `references` equals the fixture's `referenced_works` ids in order.
- [ ] `authors` has one entry per fixture authorship, in order, each with the author's OpenAlex id (prefix stripped) and display name; `institutions` and `countries` are the de-duplicated union over all authorships, in first-seen order, with `ror` and country code taken from the fixture.
- [ ] A transport returning status 404 makes `fetch_work` return `None`; status 429 and 500 raise `ClientError` carrying the status.
- [ ] The recorded request is what is sent: the test asserts the method, URL (minus the key) and key placement equal those in `tests/fixtures/README.md`. The `ClientError` message and every log record (`caplog`, all levels) never contain the key string used in the test.
- [ ] `stdlib_transport` is exercised against a local `http.server` started in the test on `127.0.0.1` (not the internet): a 200 returns status and body bytes, a 404 returns status 404 without raising, a POST body arrives byte-identical, and a 302 with a `Location` header is followed to that URL.
- [ ] Header case is preserved: the local server's handler records the raw request header names (`list(self.headers.keys())`) and the test asserts the exact, case-sensitive string `x-api-key` is among them when the transport is called with `{"x-api-key": "<test key>"}`. (This fails on `urllib`; that is the point of the test.)

## Gate

```
ruff check .
python scripts/check_tests_first.py
pytest -q
```

CI (`.github/workflows/tests.yml`) runs exactly these, with `PYTHONUTF8=1` and bogus `OPENALEX_API_KEY` / `S2_API_KEY`. Zero failures before pushing.

## Comments
