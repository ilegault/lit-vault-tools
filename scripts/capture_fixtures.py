"""Ticket 05: capture real API responses into tests/fixtures/ (run by a person, never an agent).

Usage (from the repo root):
    python scripts/capture_fixtures.py --doi 10.xxxx/yyyy --osti-title "Some DOE report title"

Keys are read from a local .env file in the repo root (gitignored), KEY=VALUE lines:
    OPENALEX_API_KEY=...      (optional for this one-off capture, but recommended)
    S2_API_KEY=...            (optional: without it you share Semantic Scholar's public pool and may get 429s)
    CROSSREF_MAILTO=you@example.com   (optional: puts you in Crossref's "polite" pool)

What it does:
  1. Makes the nine requests listed in ticket 05.
  2. Writes each response body to tests/fixtures/<name>.json byte-for-byte (unmodified).
  3. Writes tests/fixtures/README.md recording every request with keys replaced by placeholders.
  4. Checks the ticket's acceptance criteria and that no key / mailto / '@' leaked into any file.
Nothing is written until every request has succeeded, so a failed run never leaves half a fixture set.
"""

from __future__ import annotations

import argparse
import datetime as dt
import http.client
import json
import pathlib
import sys
import time
import urllib.parse

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures"

OPENALEX = "https://api.openalex.org"
S2 = "https://api.semanticscholar.org/graph/v1"  # the "Academic Graph API"
CROSSREF = "https://api.crossref.org"
OSTI = "https://www.osti.gov/api/v1"

# Lean field set for reference/citation pages (no abstract / tldr: those come from the batch call).
S2_LEAN_FIELDS = "title,year,citationCount,externalIds,isInfluential"
S2_DETAIL_FIELDS = "abstract,tldr,authors,venue"
S2_PAGE_LIMIT = 5  # small on purpose, so page 1 has a `next`
S2_SPACING_S = 3.0  # nominal limit is 1 req/s with a key, but in practice under ~3 s trips 429s
# An id Semantic Scholar does not know, so the batch fixture contains a real `null` entry.
S2_BOGUS_ID = "0000000000000000000000000000000000000000"


def load_env(path: pathlib.Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def _http(method: str, url: str, headers: dict[str, str], body: bytes | None) -> tuple[int, bytes, str | None]:
    """One request with header names sent exactly as given. Returns (status, body, Location header)."""
    parts = urllib.parse.urlsplit(url)
    conn_cls = http.client.HTTPSConnection if parts.scheme == "https" else http.client.HTTPConnection
    conn = conn_cls(parts.netloc, timeout=60)
    try:
        conn.request(method, parts.path + (f"?{parts.query}" if parts.query else ""), body=body, headers=headers)
        resp = conn.getresponse()
        return resp.status, resp.read(), resp.getheader("Location")
    finally:
        conn.close()


class Capture:
    """Makes requests, keeps raw bodies in memory, and records a redacted description of each."""

    def __init__(self, env: dict[str, str]) -> None:
        self.openalex_key = env.get("OPENALEX_API_KEY", "")
        self.s2_key = env.get("S2_API_KEY", "")
        self.mailto = env.get("CROSSREF_MAILTO", "")
        self.bodies: dict[str, bytes] = {}
        self.records: list[dict[str, str]] = []
        self._last_s2 = 0.0

    def secrets(self) -> list[str]:
        return [s for s in (self.openalex_key, self.s2_key, self.mailto) if s]

    def redact(self, text: str) -> str:
        text = text.replace(self.openalex_key or "\0", "<KEY>").replace(self.s2_key or "\0", "<KEY>")
        if self.mailto:
            text = text.replace(urllib.parse.quote(self.mailto, safe=""), "<MAILTO>").replace(self.mailto, "<MAILTO>")
        return text

    def _send(self, method: str, url: str, headers: dict[str, str], body: bytes | None) -> bytes:
        # http.client, NOT urllib: urllib re-capitalises header names ("x-api-key" -> "X-api-key"), and
        # Semantic Scholar's header is case-sensitive, so urllib silently sends requests as unauthenticated.
        for attempt in range(5):
            status, data, location = _http(method, url, headers, body)
            if status in (301, 302, 303, 307, 308) and location:
                url = urllib.parse.urljoin(url, location)
                continue
            if status == 200:
                return data
            if status == 429 and attempt < 4:
                wait = 5 * 2 ** attempt  # exponential backoff: 5, 10, 20, 40 s
                print(f"    429 rate-limited, waiting {wait}s and retrying...")
                time.sleep(wait)
                continue
            raise SystemExit(f"FAILED {status} on {method} {self.redact(url)}\n{data[:500]!r}")
        raise SystemExit(f"Gave up after repeated 429s on {method} {self.redact(url)}")

    def get(self, name: str, url: str, *, key_note: str, s2: bool = False, headers: dict[str, str] | None = None,
            method: str = "GET", body: bytes | None = None) -> object:
        headers = {"User-Agent": "lit-vault-tools/0.1 (fixture capture)", **(headers or {})}
        if s2:
            if self.s2_key:
                headers["x-api-key"] = self.s2_key
            wait = S2_SPACING_S - (time.monotonic() - self._last_s2)
            if wait > 0:
                time.sleep(wait)
        print(f"  {name}: {method} {self.redact(url)}")
        raw = self._send(method, url, headers, body)
        if s2:
            self._last_s2 = time.monotonic()
        if name:
            self.bodies[name] = raw
            shown_headers = {k: ("<KEY>" if k.lower() == "x-api-key" else v) for k, v in headers.items()
                             if k != "User-Agent"}
            self.records.append({
                "file": f"{name}.json",
                "method": method,
                "url": self.redact(url),
                "headers": json.dumps(shown_headers) if shown_headers else "(none)",
                "body": body.decode("utf-8") if body else "(none)",
                "key": key_note,
            })
        return json.loads(raw)


def capture(cap: Capture, doi: str, osti_title: str) -> None:
    doi_q = urllib.parse.quote(doi, safe="/")

    # ---- OpenAlex: key as query parameter `api_key` ----
    oa_note = "OpenAlex: query parameter `api_key=<KEY>`" + ("" if cap.openalex_key else " (captured without a key)")
    oa_key = f"?api_key={cap.openalex_key}" if cap.openalex_key else ""
    work = cap.get("openalex_work", f"{OPENALEX}/works/doi:{doi_q}{oa_key}", key_note=oa_note)
    inst_ids = [i["id"] for a in work.get("authorships", []) for i in a.get("institutions", []) if i.get("id")]
    if not inst_ids:
        raise SystemExit("This work has no institutions in OpenAlex; pick another paper.")
    inst_id = inst_ids[0].rsplit("/", 1)[-1]
    cap.get("openalex_institution", f"{OPENALEX}/institutions/{inst_id}{oa_key}", key_note=oa_note)

    # ---- Semantic Scholar (Academic Graph API): key in header `x-api-key` ----
    s2_note = "Semantic Scholar: header `x-api-key: <KEY>`" + ("" if cap.s2_key else " (captured without a key)")
    ref = f"DOI:{doi_q}"
    cap.get("s2_paper", f"{S2}/paper/{ref}?fields=paperId", key_note=s2_note, s2=True)

    base = f"{S2}/paper/{ref}/references?fields={S2_LEAN_FIELDS}&limit={S2_PAGE_LIMIT}"
    page = cap.get("s2_references_page1", f"{base}&offset=0", key_note=s2_note, s2=True)
    if not page.get("data"):
        raise SystemExit("Semantic Scholar returned no reference list for this paper (data is empty/null). "
                         "Usually the publisher (often Elsevier) hides references from S2. Pick another paper.")
    first_ids = [e["citedPaper"]["paperId"] for e in page["data"] if (e.get("citedPaper") or {}).get("paperId")]
    if "next" not in page:
        raise SystemExit("References page 1 has no `next` (too few references, or the publisher hides them "
                         "from Semantic Scholar). Pick a paper with more than 5 references visible on S2.")
    # Find the last page in ONE extra request (instead of walking 5 at a time): ask for up to 1000
    # references once (not saved), count them, then request the final short page directly.
    everything = cap.get("", f"{S2}/paper/{ref}/references?fields=title&limit=1000&offset=0", key_note=s2_note, s2=True)
    total = len(everything.get("data") or [])
    last_offset = max(total - 2, S2_PAGE_LIMIT)  # last 2 items -> offset + limit runs past the end -> no `next`
    cap.get("s2_references_last", f"{base}&offset={last_offset}", key_note=s2_note, s2=True)

    cites = cap.get("s2_citations_page1",
                    f"{S2}/paper/{ref}/citations?fields={S2_LEAN_FIELDS}&limit={S2_PAGE_LIMIT}&offset=0",
                    key_note=s2_note, s2=True)
    if not cites.get("data"):
        raise SystemExit("No citations on Semantic Scholar for this paper; pick a better-cited one.")

    batch_body = json.dumps({"ids": first_ids + [S2_BOGUS_ID]}).encode("utf-8")
    cap.get("s2_batch", f"{S2}/paper/batch?fields={S2_DETAIL_FIELDS}", key_note=s2_note, s2=True,
            method="POST", headers={"Content-Type": "application/json"}, body=batch_body)

    # ---- Crossref: no key; `mailto` query parameter for the polite pool ----
    cr_note = "Crossref: no key; `mailto=<MAILTO>` query parameter (polite pool)"
    cr_q = f"?mailto={urllib.parse.quote(cap.mailto, safe='')}" if cap.mailto else ""
    cr = cap.get("crossref_work", f"{CROSSREF}/works/{doi_q}{cr_q}", key_note=cr_note)
    if not cr.get("message", {}).get("reference"):
        raise SystemExit("Crossref has no `reference` array for this DOI (publisher didn't deposit/open them). "
                         "Pick another paper.")

    # ---- OSTI: no key; JSON via Accept header ----
    osti = cap.get("osti_record",
                   f"{OSTI}/records?title={urllib.parse.quote(osti_title)}&rows=1",
                   key_note="OSTI: no key; header `Accept: application/json`",
                   headers={"Accept": "application/json"})
    if not osti:
        raise SystemExit("OSTI returned no records for that title; try a different report title.")


def write_readme(cap: Capture, doi: str, today: str) -> str:
    lines = [
        "# Test fixtures",
        "",
        "Real, unmodified API responses captured by hand for ticket 05 (`scripts/capture_fixtures.py`).",
        f"Paper: DOI `{doi}`. Capture date for every file: {today}.",
        "",
        "## How each API expects its credentials",
        "",
        "- OpenAlex: API key as query parameter `api_key=<KEY>`.",
        "- Semantic Scholar (Academic Graph API, `https://api.semanticscholar.org/graph/v1`): "
        "API key in request header `x-api-key: <KEY>`.",
        "- Crossref: no key; contact address as query parameter `mailto=<MAILTO>` (polite pool).",
        "- OSTI.gov: no key; ask for JSON with header `Accept: application/json`.",
        "",
        "## Requests",
        "",
    ]
    for r in cap.records:
        lines += [
            f"### `{r['file']}`",
            "",
            f"- Method: `{r['method']}`",
            f"- URL: `{r['url']}`",
            f"- Headers: `{r['headers']}`",
            f"- Body: `{r['body']}`",
            f"- Credentials: {r['key']}",
            f"- Captured: {today}",
            "",
        ]
    return cap.redact("\n".join(lines))


def check(cap: Capture, readme: str) -> list[str]:
    problems = []
    if "next" not in json.loads(cap.bodies["s2_references_page1"]):
        problems.append("s2_references_page1.json has no `next`")
    if "next" in json.loads(cap.bodies["s2_references_last"]):
        problems.append("s2_references_last.json still has `next`")
    if not json.loads(cap.bodies["openalex_work"]).get("referenced_works"):
        problems.append("openalex_work.json has empty referenced_works")
    texts = {f"{n}.json": b.decode("utf-8", "replace") for n, b in cap.bodies.items()}
    texts["README.md"] = readme
    for fname, text in texts.items():
        for secret in cap.secrets():
            if secret in text:
                problems.append(f"{fname} contains a key or mailto value")
        if "@" in text:
            problems.append(f"{fname} contains '@' (check it isn't an email; ticket wants none)")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--doi", required=True, help="DOI of one well-cited ion-irradiation paper")
    parser.add_argument("--osti-title", required=True, help="title of one DOE technical report on osti.gov")
    args = parser.parse_args()

    doi = args.doi.strip().lower().removeprefix("https://doi.org/").removeprefix("doi:")
    cap = Capture(load_env(REPO_ROOT / ".env"))
    for name, val in (("OPENALEX_API_KEY", cap.openalex_key), ("S2_API_KEY", cap.s2_key),
                      ("CROSSREF_MAILTO", cap.mailto)):
        print(f"{name}: {'found' if val else 'not set (continuing without it)'}")

    capture(cap, doi, args.osti_title)
    today = dt.date.today().isoformat()
    readme = write_readme(cap, doi, today)

    FIXTURES.mkdir(parents=True, exist_ok=True)
    for name, raw in cap.bodies.items():
        (FIXTURES / f"{name}.json").write_bytes(raw)
    (FIXTURES / "README.md").write_text(readme, encoding="utf-8", newline="\n")
    print(f"\nWrote {len(cap.bodies)} fixtures + README.md to {FIXTURES}")

    problems = check(cap, readme)
    for p in problems:
        print("CHECK:", p)
    if not problems:
        print("All automatic checks passed.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
