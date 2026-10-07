"""enrich: author, institution and subfield notes. Real vault files; fake transport replays real fixtures."""

import datetime
import json
from pathlib import Path

from lit_vault_tools.clients.http import HttpResponse
from lit_vault_tools.commands.enrich import run_enrich
from lit_vault_tools.domain.frontmatter import read_list, read_scalar, split_note

FIXTURES = Path(__file__).parent / "fixtures"
WORK = json.loads((FIXTURES / "openalex_work.json").read_text(encoding="utf-8"))
INSTITUTION = json.loads((FIXTURES / "openalex_institution.json").read_text(encoding="utf-8"))
DOI = "10.1016/j.matdes.2024.112730"
TODAY = datetime.date(2026, 10, 1)
PREFIX = "https://openalex.org/"

PAPER = f"---\ntype: paper\ncitekey: agrawal2024\ndoi: {DOI}\n---\nMy own reading notes.\n"


class FakeTransport:
    def __init__(self, work=None, geo=True):
        self.work = WORK if work is None else work
        self.geo = geo
        self.work_calls = 0
        self.institution_calls = 0

    def __call__(self, method, url, headers, body):
        if "/institutions/" in url:
            self.institution_calls += 1
            raw = INSTITUTION
            if not self.geo:
                raw = json.loads(json.dumps(INSTITUTION))
                raw["geo"]["latitude"] = raw["geo"]["longitude"] = None
            return HttpResponse(200, json.dumps(raw).encode())
        self.work_calls += 1
        return HttpResponse(200, json.dumps(self.work).encode())


def make(vault: Path, rel: str, text: str) -> Path:
    path = vault / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    return path


def tree(vault: Path) -> dict[str, bytes]:
    return {str(p.relative_to(vault)): p.read_bytes() for p in sorted(vault.rglob("*")) if p.is_file()}


def parts_of(path: Path):
    return split_note(path.read_text(encoding="utf-8"))


def strip(value: str) -> str:
    return value.removeprefix(PREFIX)


def links(parts, key):
    return [item.removeprefix("[[").removesuffix("]]") for item in read_list(parts, key)]


def test_paper_links_and_people_notes_match_fixture(tmp_path):
    paper = make(tmp_path, "p.md", PAPER)
    run_enrich(tmp_path, None, "k", FakeTransport(), TODAY)
    parts = parts_of(paper)
    assert all(v.startswith("[[") and v.endswith("]]") for v in read_list(parts, "authors"))

    author_ids = {a["author"]["id"] for a in WORK["authorships"]}
    names = links(parts, "authors")
    assert len(names) == len(WORK["authorships"])
    for authorship, name in zip(WORK["authorships"], names, strict=True):
        note = parts_of(tmp_path / "Authors" / f"{name}.md")
        assert read_scalar(note, "type") == "author"
        assert read_scalar(note, "openalex_id") == strip(authorship["author"]["id"])
    assert len(list((tmp_path / "Authors").glob("*.md"))) == len(author_ids)

    # a raw-name variant differing from the display name becomes an alias
    megha = parts_of(tmp_path / "Authors" / "Megha N. Dubey.md")
    assert read_list(megha, "aliases") == ["Megha Dubey"]
    plain = parts_of(tmp_path / "Authors" / "Lin Shao.md")
    assert read_list(plain, "aliases") == []

    institutions = {i["id"]: i for a in WORK["authorships"] for i in a["institutions"]}
    assert len(links(parts, "institutions")) == len(institutions)
    for raw in institutions.values():
        note = parts_of(tmp_path / "Institutions" / f"{raw['display_name']}.md")
        assert read_scalar(note, "type") == "institution"
        assert read_scalar(note, "openalex_id") == strip(raw["id"])
        assert read_scalar(note, "country") == raw["country_code"]

    subfield = WORK["primary_topic"]["subfield"]
    assert links(parts, "subfield") == [subfield["display_name"]]
    note = parts_of(tmp_path / "Subfields" / f"{subfield['display_name']}.md")
    assert read_scalar(note, "type") == "subfield"
    assert read_scalar(note, "openalex_id") == subfield["id"].rsplit("/", 1)[-1]


def test_rerun_changes_nothing_in_the_whole_tree(tmp_path):
    make(tmp_path, "p.md", PAPER)
    run_enrich(tmp_path, None, "k", FakeTransport(), TODAY)
    before = tree(tmp_path)
    mtimes = {p: p.stat().st_mtime_ns for p in tmp_path.rglob("*.md")}
    transport = FakeTransport()
    run_enrich(tmp_path, None, "k", transport, datetime.date(2026, 12, 1))
    assert tree(tmp_path) == before
    assert {p: p.stat().st_mtime_ns for p in tmp_path.rglob("*.md")} == mtimes
    assert transport.institution_calls == 0


def collision_work(author_id: str, institution: str, inst_id: str):
    work = json.loads(json.dumps(WORK))
    work["authorships"] = [
        {
            "author": {"id": PREFIX + author_id, "display_name": "Jane Doe"},
            "raw_author_name": "Jane Doe",
            "institutions": [
                {"id": PREFIX + inst_id, "display_name": institution, "ror": None, "country_code": "US", "type": "x"}
            ],
            "countries": ["US"],
        }
    ]
    return work


class SwitchingTransport(FakeTransport):
    def __init__(self, works):
        super().__init__()
        self.works = works

    def __call__(self, method, url, headers, body):
        if "/institutions/" in url:
            return super().__call__(method, url, headers, body)
        for doi, work in self.works.items():
            if f"doi:{doi}" in url:
                return HttpResponse(200, json.dumps(work).encode())
        raise AssertionError(url)


def two_papers(vault: Path):
    make(vault, "a.md", "---\ntype: paper\ndoi: 10.1000/aaa\n---\nA\n")
    make(vault, "b.md", "---\ntype: paper\ndoi: 10.1000/bbb\n---\nB\n")
    return {
        "10.1000/aaa": collision_work("A1", "Oak Ridge", "I1"),
        "10.1000/bbb": collision_work("A2", "Boise State", "I2"),
    }


def test_same_display_name_different_ids_get_disambiguated_files(tmp_path):
    works = two_papers(tmp_path)
    run_enrich(tmp_path, None, "k", SwitchingTransport(works), TODAY)
    assert sorted(p.name for p in (tmp_path / "Authors").glob("*.md")) == ["Jane Doe (Boise State).md", "Jane Doe.md"]
    assert read_scalar(parts_of(tmp_path / "Authors" / "Jane Doe.md"), "openalex_id") == "A1"
    assert read_scalar(parts_of(tmp_path / "Authors" / "Jane Doe (Boise State).md"), "openalex_id") == "A2"


def test_reversed_order_on_rerun_renames_nothing(tmp_path):
    works = two_papers(tmp_path)
    run_enrich(tmp_path, None, "k", SwitchingTransport(works), TODAY)
    before = tree(tmp_path)
    run_enrich(tmp_path, [tmp_path / "b.md", tmp_path / "a.md"], "k", SwitchingTransport(works), TODAY)
    assert tree(tmp_path) == before


def megha_id() -> str:
    authorship = next(a for a in WORK["authorships"] if a["author"]["display_name"] == "Megha N. Dubey")
    return strip(authorship["author"]["id"])


def test_existing_author_body_survives_and_aliases_grow(tmp_path):
    make(tmp_path, "p.md", PAPER)
    body = "Typed by the developer.\n\n- my thoughts\n"
    path = make(
        tmp_path,
        "Authors/Megha N. Dubey.md",
        f'---\ntype: author\nopenalex_id: "{megha_id()}"\naliases: ["M. Dubey"]\n---\n{body}',
    )
    run_enrich(tmp_path, None, "k", FakeTransport(), TODAY)
    parts = parts_of(path)
    assert parts.body == body
    assert read_list(parts, "aliases") == ["M. Dubey", "Megha Dubey"]
    assert len(list((tmp_path / "Authors").glob("*.md"))) == len({a["author"]["id"] for a in WORK["authorships"]})


def test_hand_renamed_author_is_found_by_id_and_linked(tmp_path):
    paper = make(tmp_path, "p.md", PAPER)
    text = f'---\ntype: author\nopenalex_id: "{megha_id()}"\naliases: []\n---\nmine\n'
    renamed = make(tmp_path, "Authors/Dr Dubey (my name for her).md", text)
    run_enrich(tmp_path, None, "k", FakeTransport(), TODAY)
    assert "[[Dr Dubey (my name for her)]]" in read_list(parts_of(paper), "authors")
    assert not (tmp_path / "Authors" / "Megha N. Dubey.md").exists()
    assert renamed.read_text(encoding="utf-8").endswith("---\nmine\n")


def test_unrelated_existing_file_is_never_overwritten(tmp_path):
    make(tmp_path, "p.md", PAPER)
    mine = make(tmp_path, "Authors/Lin Shao.md", "---\ntype: author\n---\nno id here\n")
    run_enrich(tmp_path, None, "k", FakeTransport(), TODAY)
    assert mine.read_bytes() == b"---\ntype: author\n---\nno id here\n"
    assert (tmp_path / "Authors" / "Lin Shao (2).md").exists() or any(
        "Lin Shao (" in p.name for p in (tmp_path / "Authors").glob("*.md")
    )


def test_institution_location_from_geo_lookup(tmp_path):
    make(tmp_path, "p.md", PAPER)
    run_enrich(tmp_path, None, "k", FakeTransport(), TODAY)
    expected = f"{INSTITUTION['geo']['latitude']},{INSTITUTION['geo']['longitude']}"
    note = tmp_path / "Institutions" / "University of North Texas.md"
    assert f"\nlocation: {expected}\n" in note.read_text(encoding="utf-8")


def test_unknown_location_is_omitted_never_zero(tmp_path):
    make(tmp_path, "p.md", PAPER)
    run_enrich(tmp_path, None, "k", FakeTransport(geo=False), TODAY)
    for note in (tmp_path / "Institutions").glob("*.md"):
        text = note.read_text(encoding="utf-8")
        assert "location" not in text and "0,0" not in text


def test_location_found_later_is_added_to_existing_note(tmp_path):
    make(tmp_path, "p.md", PAPER)
    run_enrich(tmp_path, None, "k", FakeTransport(geo=False), TODAY)
    run_enrich(tmp_path, None, "k", FakeTransport(geo=True), TODAY)
    text = (tmp_path / "Institutions" / "University of North Texas.md").read_text(encoding="utf-8")
    assert "\nlocation: " in text


def test_geo_cache_is_read_on_second_run(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    make(vault, "p.md", PAPER)
    first = FakeTransport()
    run_enrich(vault, None, "k", first, TODAY)
    assert first.institution_calls > 0
    # a fresh vault with the same cache: no institution request at all
    other = tmp_path / "other"
    make(other, "p.md", PAPER)
    second = FakeTransport()
    run_enrich(other, None, "k", second, TODAY)
    assert second.institution_calls == 0
    assert (other / "Institutions" / "University of North Texas.md").read_text(encoding="utf-8").count("location") == 1
