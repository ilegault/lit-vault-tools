"""refs / cited_by between saved papers: real notes in a temp vault, fake transport replaying the real work shape."""

import datetime
import json
from pathlib import Path

from lit_vault_tools.clients.http import HttpResponse
from lit_vault_tools.commands.enrich import run_enrich
from lit_vault_tools.domain.doi import PaperIds
from lit_vault_tools.domain.frontmatter import read_list, read_scalar, split_note
from lit_vault_tools.domain.links import cited_by_map, resolve_refs

WORK = json.loads((Path(__file__).parent / "fixtures" / "openalex_work.json").read_text(encoding="utf-8"))
D0 = datetime.date(2026, 9, 1)
D1 = datetime.date(2026, 10, 1)
D2 = datetime.date(2026, 11, 1)
PREFIX = "https://openalex.org/"

DOI_A, DOI_B, DOI_C = "10.1000/aaa", "10.1000/bbb", "10.1000/ccc"
ID_A, ID_B, ID_C = "W1001", "W1002", "W1003"


class LinkTransport:
    """Serves the real work shape with `id` and `referenced_works` rewritten per DOI."""

    def __init__(self, refs: dict[str, list[str]]):
        self.refs = refs  # doi -> referenced OpenAlex ids
        self.ids = {DOI_A: ID_A, DOI_B: ID_B, DOI_C: ID_C}

    def __call__(self, method, url, headers, body):
        if "/institutions/" in url:
            return HttpResponse(404, b"{}")
        doi = url.split("doi:")[1].split("?")[0]
        work = json.loads(json.dumps(WORK))
        work["id"] = PREFIX + self.ids[doi]
        work["doi"] = "https://doi.org/" + doi
        work["referenced_works"] = [PREFIX + r for r in self.refs.get(doi, [])]
        return HttpResponse(200, json.dumps(work).encode())


def make_vault(vault: Path) -> dict[str, Path]:
    paths = {}
    for stem, doi in (("@alpha2020", DOI_A), ("@beta2021", DOI_B), ("@gamma2022", DOI_C)):
        path = vault / f"{stem}.md"
        text = f"---\ntype: paper\ncitekey: {stem[1:]}\ndoi: {doi}\n---\nMy notes on {stem}.\n"
        path.write_text(text, encoding="utf-8")
        paths[stem] = path
    return paths


def fm(path: Path):
    return split_note(path.read_text(encoding="utf-8"))


def test_reference_between_saved_papers_links_both_ways(tmp_path):
    notes = make_vault(tmp_path)
    run_enrich(tmp_path, None, "k", LinkTransport({}), D0)
    assert read_list(fm(notes["@beta2021"]), "cited_by") == []
    run_enrich(tmp_path, None, "k", LinkTransport({DOI_A: [ID_B]}), D1)
    assert read_list(fm(notes["@alpha2020"]), "refs") == ["[[@beta2021]]"]
    beta = fm(notes["@beta2021"])
    assert read_list(beta, "cited_by") == ["[[@alpha2020]]"]
    assert read_scalar(beta, "enriched_on") == "2026-10-01"
    assert read_scalar(fm(notes["@gamma2022"]), "enriched_on") == "2026-09-01"


def test_unsaved_references_never_appear(tmp_path):
    notes = make_vault(tmp_path)
    run_enrich(tmp_path, None, "k", LinkTransport({DOI_A: [ID_B, "W999999"]}), D1)
    assert read_list(fm(notes["@alpha2020"]), "refs") == ["[[@beta2021]]"]
    for note in notes.values():
        assert "W999999" not in note.read_text(encoding="utf-8")


def test_refs_and_cited_by_sorted_by_stem_regardless_of_order(tmp_path):
    notes = make_vault(tmp_path)
    run_enrich(tmp_path, None, "k", LinkTransport({DOI_A: [ID_C, ID_B], DOI_B: [ID_C]}), D1)
    assert read_list(fm(notes["@alpha2020"]), "refs") == ["[[@beta2021]]", "[[@gamma2022]]"]
    assert read_list(fm(notes["@gamma2022"]), "cited_by") == ["[[@alpha2020]]", "[[@beta2021]]"]


def test_enriching_one_note_updates_the_others_cited_by_and_rerun_is_a_noop(tmp_path):
    notes = make_vault(tmp_path)
    run_enrich(tmp_path, None, "k", LinkTransport({}), D0)
    run_enrich(tmp_path, [notes["@alpha2020"]], "k", LinkTransport({DOI_A: [ID_B]}), D1)
    assert read_list(fm(notes["@beta2021"]), "cited_by") == ["[[@alpha2020]]"]
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in tmp_path.glob("*.md")}
    run_enrich(tmp_path, [notes["@alpha2020"]], "k", LinkTransport({DOI_A: [ID_B]}), D2)
    assert {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in tmp_path.glob("*.md")} == before


def test_stale_link_is_removed_when_the_note_is_deleted(tmp_path):
    notes = make_vault(tmp_path)
    transport = LinkTransport({DOI_A: [ID_B]})
    run_enrich(tmp_path, None, "k", transport, D1)
    assert read_list(fm(notes["@alpha2020"]), "refs") == ["[[@beta2021]]"]
    notes["@beta2021"].unlink()
    run_enrich(tmp_path, [notes["@alpha2020"]], "k", transport, D2)
    alpha = fm(notes["@alpha2020"])
    assert read_list(alpha, "refs") == []
    assert read_scalar(alpha, "enriched_on") == "2026-11-01"


def test_body_and_zotero_lines_survive_link_writing(tmp_path):
    notes = make_vault(tmp_path)
    run_enrich(tmp_path, None, "k", LinkTransport({DOI_A: [ID_B]}), D1)
    for stem, note in notes.items():
        parts = fm(note)
        assert parts.body == f"My notes on {stem}.\n"
        assert read_scalar(parts, "type") == "paper"


def candidates():
    return [
        ("@alpha2020", PaperIds(doi="10.1000/aaa", openalex_id="W1")),
        ("@beta2021", PaperIds(doi="10.1000/bbb", openalex_id="W2")),
        ("@gamma2022", PaperIds(doi="10.1000/ccc")),
    ]


def test_resolve_refs_matches_by_openalex_id_and_by_doi_in_any_form():
    refs = resolve_refs(["W2", "W404"], ["https://doi.org/10.1000/CCC", "10.1000/zzz"], candidates(), own="@alpha2020")
    assert refs == ["@beta2021", "@gamma2022"]


def test_resolve_refs_never_links_a_paper_to_itself_and_deduplicates():
    refs = resolve_refs(["W1", "W2"], ["10.1000/bbb"], candidates(), own="@alpha2020")
    assert refs == ["@beta2021"]


def test_cited_by_map_inverts_refs_and_sorts():
    result = cited_by_map({"@b": ["@c"], "@a": ["@c", "@b"], "@c": []})
    assert result == {"@c": ["@a", "@b"], "@b": ["@a"]}
