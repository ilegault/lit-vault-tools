"""enrich end to end on a temporary vault: real note files, fake transport replaying the real OpenAlex response."""

import datetime
import json
from pathlib import Path

import pytest

from lit_vault_tools.cli import build_parser, main
from lit_vault_tools.clients.http import HttpResponse
from lit_vault_tools.commands.enrich import run_enrich
from lit_vault_tools.domain.frontmatter import read_list, read_scalar, split_note

FIXTURE = Path(__file__).parent / "fixtures" / "openalex_work.json"
RAW = json.loads(FIXTURE.read_text(encoding="utf-8"))
DOI = "10.1016/j.matdes.2024.112730"
D1 = datetime.date(2026, 10, 1)
D2 = datetime.date(2026, 11, 5)

PAPER = (
    "---\n"
    "type: paper\n"
    "citekey: agrawal2024\n"
    f"doi: {DOI}\n"
    "title: Some title\n"
    "abstract: |\n"
    "  First line of abstract.\n"
    "  Second line.\n"
    "---\n"
    "My own reading notes.\n"
    "\n"
    "- a bullet I typed\n"
)


class FakeTransport:
    """Replays the fixture; `plan` maps a DOI to a status or a raw payload override."""

    def __init__(self, raw=None, plan=None):
        self.raw = RAW if raw is None else raw
        self.plan = plan or {}
        self.calls = []

    def __call__(self, method, url, headers, body):
        self.calls.append(url)
        for doi, status in self.plan.items():
            if f"doi:{doi}" in url:
                return HttpResponse(status, b"{}")
        return HttpResponse(200, json.dumps(self.raw).encode())


def make(vault: Path, rel: str, text: str) -> Path:
    path = vault / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    return path


def snapshot(vault: Path) -> dict[str, bytes]:
    return {str(p.relative_to(vault)): p.read_bytes() for p in sorted(vault.rglob("*")) if p.is_file()}


def test_parser_vault_and_notes():
    args = build_parser().parse_args(["enrich", "--vault", "V", "a.md"])
    assert args.vault == "V"
    assert args.notes == ["a.md"]


def test_main_without_key_exits_2_and_makes_no_call(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    make(tmp_path, "p.md", PAPER)
    transport = FakeTransport()
    assert main(["enrich", "--vault", str(tmp_path)], transport=transport) == 2
    assert capsys.readouterr().err
    assert transport.calls == []


def test_env_file_supplies_key_and_environment_overrides(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    vault = tmp_path / "vault"
    make(vault, "p.md", PAPER)
    (tmp_path / ".env").write_text("# comment\nOPENALEX_API_KEY=from-file\n", encoding="utf-8")
    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    transport = FakeTransport()
    assert main(["enrich", "--vault", str(vault)], transport=transport) == 0
    assert "api_key=from-file" in transport.calls[0]

    monkeypatch.setenv("OPENALEX_API_KEY", "from-env")
    transport = FakeTransport()
    main(["enrich", "--vault", str(vault)], transport=transport)
    assert "api_key=from-env" in transport.calls[0]


def test_vault_falls_back_to_environment(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    vault = tmp_path / "vault"
    make(vault, "p.md", PAPER)
    monkeypatch.setenv("OPENALEX_API_KEY", "k")
    monkeypatch.setenv("LIT_VAULT_DIR", str(vault))
    assert main(["enrich"], transport=FakeTransport()) == 0
    assert "enrich_status: ok" in (vault / "p.md").read_text(encoding="utf-8")


def test_enrich_fills_values_and_preserves_everything_else(tmp_path):
    note = make(tmp_path, "p.md", PAPER)
    summary = run_enrich(tmp_path, None, "k", FakeTransport(), D1)
    assert summary.ok == 1
    before, after = split_note(PAPER), split_note(note.read_text(encoding="utf-8"))
    assert after.body == before.body
    assert [line for line in after.lines if line in before.lines] == list(before.lines)
    assert read_scalar(after, "openalex_id") == RAW["id"].removeprefix("https://openalex.org/")
    assert read_scalar(after, "oa_status") == RAW["open_access"]["oa_status"]
    assert read_list(after, "countries") == ["US"]
    assert read_scalar(after, "enrich_status") == "ok"
    assert read_scalar(after, "enriched_on") == "2026-10-01"


def test_only_paper_notes_are_processed(tmp_path):
    make(tmp_path, "p.md", PAPER)
    others = {
        "Jane Doe.md": f"---\ntype: author\ndoi: {DOI}\n---\nbio\n",
        "_explore/stub.md": "---\ntype: stub\ndoi: 10.1000/unrelated-stub\n---\n",  # no saved paper has this DOI
        "misc.md": f"---\ntitle: x\ndoi: {DOI}\n---\nbody\n",
    }
    for rel, text in others.items():
        make(tmp_path, rel, text)
    run_enrich(tmp_path, None, "k", FakeTransport(), D1)
    for rel, text in others.items():
        assert (tmp_path / rel).read_bytes() == text.encode()


def test_explicit_note_that_is_not_a_paper_is_left_alone(tmp_path):
    author = make(tmp_path, "Jane.md", f"---\ntype: author\ndoi: {DOI}\n---\n")
    before = author.read_bytes()
    summary = run_enrich(tmp_path, [author], "k", FakeTransport(), D1)
    assert author.read_bytes() == before
    assert summary.ok == 0


def test_second_run_is_byte_and_mtime_identical(tmp_path):
    note = make(tmp_path, "p.md", PAPER)
    run_enrich(tmp_path, None, "k", FakeTransport(), D1)
    bytes_before, mtime_before = note.read_bytes(), note.stat().st_mtime_ns
    run_enrich(tmp_path, None, "k", FakeTransport(), D2)
    assert note.read_bytes() == bytes_before
    assert note.stat().st_mtime_ns == mtime_before


def test_upstream_change_updates_only_that_line_and_enriched_on(tmp_path):
    note = make(tmp_path, "p.md", PAPER)
    run_enrich(tmp_path, None, "k", FakeTransport(), D1)
    first = note.read_text(encoding="utf-8").splitlines()
    changed = json.loads(json.dumps(RAW))
    changed["open_access"]["oa_status"] = "bronze"
    run_enrich(tmp_path, None, "k", FakeTransport(changed), D2)
    second = note.read_text(encoding="utf-8").splitlines()
    differing = {a.split(":")[0] for a, b in zip(first, second, strict=True) if a != b}
    assert differing == {"oa_status", "enriched_on"}
    assert "oa_status: bronze" in second and "enriched_on: 2026-11-05" in second


def test_no_doi_not_found_error_and_the_run_continues(tmp_path):
    no_doi = make(tmp_path, "a_nodoi.md", "---\ntype: paper\ncitekey: a\n---\nbody a\n")
    missing = make(tmp_path, "b_missing.md", "---\ntype: paper\ndoi: 10.1000/missing\n---\nbody b\n")
    broken_text = "---\ntype: paper\ndoi: 10.1000/broken\n---\nbody c\n"
    broken = make(tmp_path, "c_broken.md", broken_text)
    good = make(tmp_path, "d_good.md", PAPER)
    transport = FakeTransport(plan={"10.1000/missing": 404, "10.1000/broken": 500})
    summary = run_enrich(tmp_path, None, "k", transport, D1)
    assert (summary.ok, summary.no_doi, summary.not_found, summary.error) == (1, 1, 1, 1)
    assert read_scalar(split_note(no_doi.read_text(encoding="utf-8")), "enrich_status") == "no_doi"
    assert read_scalar(split_note(missing.read_text(encoding="utf-8")), "enrich_status") == "not_found"
    assert broken.read_bytes() == broken_text.encode()
    assert read_scalar(split_note(good.read_text(encoding="utf-8")), "enrich_status") == "ok"


@pytest.mark.parametrize(("plan", "code"), [({DOI: 500}, 1), ({DOI: 404}, 0), ({}, 0)])
def test_exit_code_is_1_only_when_a_note_errored(tmp_path, monkeypatch, plan, code):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENALEX_API_KEY", "k")
    vault = tmp_path / "vault"
    make(vault, "p.md", PAPER)
    assert main(["enrich", "--vault", str(vault)], transport=FakeTransport(plan=plan)) == code


def test_crlf_note_stays_crlf(tmp_path):
    text = PAPER.replace("\n", "\r\n")
    note = make(tmp_path, "p.md", text)
    run_enrich(tmp_path, None, "k", FakeTransport(), D1)
    out = note.read_bytes()
    assert out.count(b"\n") == out.count(b"\r\n")
    assert out.endswith(b"- a bullet I typed\r\n")
