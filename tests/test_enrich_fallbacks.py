"""enrich fallbacks (Crossref, OSTI) and s2_id: a URL-routing fake transport replaying the real fixtures."""

import datetime
import json
import logging
from pathlib import Path

from lit_vault_tools.clients import crossref
from lit_vault_tools.clients.http import HttpResponse
from lit_vault_tools.clients.semantic_scholar import Pacer
from lit_vault_tools.commands.enrich import run_enrich
from lit_vault_tools.domain.frontmatter import read_list, read_scalar, split_note

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


WORK, CROSSREF, OSTI, S2 = load("openalex_work"), load("crossref_work"), load("osti_record"), load("s2_paper")
DOI = "10.1016/j.matdes.2024.112730"
CITED_DOI = next(r["DOI"] for r in CROSSREF["message"]["reference"] if r.get("DOI"))
MAILTO = "someone-test@example.org"
TODAY = datetime.date(2026, 10, 1)


class Router:
    """Routes by host. `status` overrides per service; `openalex_missing` lists DOIs OpenAlex 404s."""

    def __init__(self, openalex=200, crossref=200, osti="hit", s2=200):
        self.openalex, self.crossref, self.osti, self.s2 = openalex, crossref, osti, s2
        self.urls = []

    def __call__(self, method, url, headers, body):
        self.urls.append(url)
        if "api.openalex.org/institutions" in url:
            return HttpResponse(404, b"{}")
        if "api.openalex.org" in url:
            return self._answer(self.openalex, WORK)
        if "api.crossref.org" in url:
            return self._answer(self.crossref, CROSSREF)
        if "osti.gov" in url:
            return self._answer(200 if self.osti != 500 else 500, [] if self.osti == "empty" else OSTI)
        if "semanticscholar.org" in url:
            return self._answer(self.s2, S2)
        raise AssertionError(url)

    @staticmethod
    def _answer(status, payload):
        return HttpResponse(status, json.dumps(payload).encode() if status == 200 else b"{}")

    def called(self, host):
        return [u for u in self.urls if host in u]


def run(vault, transport, notes=None, mailto=MAILTO, s2_key="s2-key"):
    return run_enrich(
        vault,
        notes,
        "k",
        transport,
        TODAY,
        crossref_mailto=mailto,
        s2_api_key=s2_key,
        s2_pacer=Pacer(sleep=lambda s: None),
    )


def make(vault: Path, name: str, text: str) -> Path:
    path = vault / name
    path.write_bytes(text.encode("utf-8"))
    return path


def paper(doi=DOI, title="Understanding bubble and void nucleation"):
    doi_line = f"doi: {doi}\n" if doi else ""
    return f"---\ntype: paper\ncitekey: k\n{doi_line}title: {title}\nabstract: |\n  Zotero text.\n---\nMy notes.\n"


def status_of(path):
    return read_scalar(split_note(path.read_text(encoding="utf-8")), "enrich_status")


def test_crossref_hit_after_openalex_404_is_partial_and_record_is_kept(tmp_path):
    text = paper()
    note = make(tmp_path, "p.md", text)
    summary = run(tmp_path, Router(openalex=404))
    parts = split_note(note.read_text(encoding="utf-8"))
    original = split_note(text)
    assert read_scalar(parts, "enrich_status") == "partial"
    assert read_scalar(parts, "openalex_id") is None
    assert parts.body == original.body
    assert [line for line in parts.lines if line in original.lines] == list(original.lines)
    assert summary.partial == 1
    expected = crossref.fetch_work(DOI, MAILTO, Router())
    assert summary.records[note] == expected
    assert expected.reference_dois


def test_crossref_reference_dois_link_to_saved_papers(tmp_path):
    a = make(tmp_path, "@a.md", paper())
    b = make(tmp_path, "@b.md", f"---\ntype: paper\ndoi: {CITED_DOI.upper()}\n---\nB body\n")
    run(tmp_path, Router(openalex=404), notes=[a])
    assert read_list(split_note(a.read_text(encoding="utf-8")), "refs") == ["[[@b]]"]
    assert read_list(split_note(b.read_text(encoding="utf-8")), "cited_by") == ["[[@a]]"]


def test_openalex_404_and_crossref_404_is_not_found(tmp_path):
    note = make(tmp_path, "p.md", paper())
    run(tmp_path, Router(openalex=404, crossref=404))
    assert status_of(note) == "not_found"


def test_no_doi_with_osti_hit_is_partial(tmp_path):
    note = make(tmp_path, "p.md", paper(doi=None, title=OSTI[0]["title"]))
    router = Router()
    summary = run(tmp_path, router)
    assert status_of(note) == "partial"
    assert summary.records[note].doi == OSTI[0]["doi"].lower()
    assert router.called("api.openalex.org") == []


def test_no_doi_with_empty_osti_is_no_doi(tmp_path):
    note = make(tmp_path, "p.md", paper(doi=None))
    run(tmp_path, Router(osti="empty"))
    assert status_of(note) == "no_doi"


def test_no_doi_and_no_title_is_no_doi_without_calling_osti(tmp_path):
    note = make(tmp_path, "p.md", "---\ntype: paper\ncitekey: k\n---\nbody\n")
    router = Router()
    run(tmp_path, router)
    assert status_of(note) == "no_doi"
    assert router.called("osti.gov") == []


def test_s2_id_is_written_and_second_run_is_identical(tmp_path):
    note = make(tmp_path, "p.md", paper())
    run(tmp_path, Router())
    assert read_scalar(split_note(note.read_text(encoding="utf-8")), "s2_id") == S2["paperId"]
    assert status_of(note) == "ok"
    before, mtime = note.read_bytes(), note.stat().st_mtime_ns
    run_enrich(
        tmp_path, None, "k", Router(), datetime.date(2026, 12, 1),
        crossref_mailto=MAILTO, s2_api_key="s2-key", s2_pacer=Pacer(sleep=lambda s: None),
    )  # fmt: skip
    assert note.read_bytes() == before and note.stat().st_mtime_ns == mtime


def test_s2_404_leaves_s2_id_out_and_status_ok(tmp_path):
    note = make(tmp_path, "p.md", paper())
    run(tmp_path, Router(s2=404))
    parts = split_note(note.read_text(encoding="utf-8"))
    assert read_scalar(parts, "s2_id") is None
    assert read_scalar(parts, "enrich_status") == "ok"


def test_s2_error_does_not_change_status(tmp_path):
    note = make(tmp_path, "p.md", paper())
    summary = run(tmp_path, Router(s2=500))
    assert status_of(note) == "ok" and summary.ok == 1
    assert read_scalar(split_note(note.read_text(encoding="utf-8")), "s2_id") is None


def test_no_s2_key_skips_s2(tmp_path):
    note = make(tmp_path, "p.md", paper())
    router = Router()
    run(tmp_path, router, s2_key=None)
    assert router.called("semanticscholar.org") == []
    assert read_scalar(split_note(note.read_text(encoding="utf-8")), "s2_id") is None


def test_missing_mailto_skips_crossref_entirely(tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    note = make(tmp_path, "p.md", paper())
    router = Router(openalex=404)
    run(tmp_path, router, mailto=None)
    assert router.called("api.crossref.org") == []
    assert status_of(note) == "not_found"


def test_fallback_client_error_is_error_untouched_and_run_continues(tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    broken = make(tmp_path, "a_broken.md", paper())
    before = broken.read_bytes()
    nodoi_text = paper(doi=None, title="x")
    other = make(tmp_path, "b_other.md", nodoi_text)
    summary = run(tmp_path, Router(openalex=404, crossref=500, osti="empty"))
    assert broken.read_bytes() == before
    assert summary.error == 1 and summary.no_doi == 1
    assert status_of(other) == "no_doi"
    assert all(MAILTO not in r.getMessage() and MAILTO not in str(r.__dict__) for r in caplog.records)


def test_osti_client_error_is_error_untouched(tmp_path):
    note = make(tmp_path, "p.md", paper(doi=None))
    before = note.read_bytes()
    summary = run(tmp_path, Router(osti=500))
    assert note.read_bytes() == before and summary.error == 1
