"""explore --more: add the next 200 ranked neighbors per list without wiping anything."""

import hashlib
import json
import re
from pathlib import Path

from lit_vault_tools.cli import build_parser, main
from lit_vault_tools.clients.http import ClientError, HttpResponse
from lit_vault_tools.clients.semantic_scholar import Pacer
from lit_vault_tools.commands.explore import run_explore
from lit_vault_tools.domain.neighbors import Neighbor, rank_neighbors
from lit_vault_tools.domain.stubs import read_stub_ids

FIXTURES = Path(__file__).parent / "fixtures"
REF_ITEM = json.loads((FIXTURES / "s2_references_page1.json").read_text(encoding="utf-8"))["data"][0]
CIT_ITEM = json.loads((FIXTURES / "s2_citations_page1.json").read_text(encoding="utf-8"))["data"][0]
BATCH_ENTRY = next(e for e in json.loads((FIXTURES / "s2_batch.json").read_text(encoding="utf-8")) if e)
DOI = "10.1016/j.matdes.2024.112730"
FOCUS = f"---\ntype: paper\ncitekey: focus2024\ndoi: {DOI}\n---\nMy own notes.\n"


def ref_item(i: int) -> dict:
    paper = dict(REF_ITEM["citedPaper"], paperId=f"R{i:04d}", title=f"Paper R{i}", citationCount=(i * 37) % 101)
    paper["externalIds"] = {"DOI": f"10.9999/r{i}"}
    return {"isInfluential": i % 17 == 0, "citedPaper": paper}


def cit_item(i: int) -> dict:
    paper = dict(CIT_ITEM["citingPaper"], paperId=f"C{i:04d}", title=f"Paper C{i}", citationCount=i)
    paper["externalIds"] = {"DOI": f"10.9999/c{i}"}
    return {"isInfluential": False, "citingPaper": paper}


class Upstream:
    def __init__(self, refs, cits, fail=False):
        self.refs, self.cits, self.fail = refs, cits, fail
        self.posted = []

    def __call__(self, method, url, headers, body):
        if self.fail:
            raise ClientError(500, url)
        if method == "POST":
            ids = json.loads(body)["ids"]
            self.posted.extend(ids)
            return HttpResponse(200, json.dumps([{**BATCH_ENTRY, "paperId": i} for i in ids]).encode())
        items = self.refs if "/references?" in url else self.cits
        return HttpResponse(200, json.dumps({"offset": 0, "data": items}).encode())


def make(tmp_path):
    focus = tmp_path / "@focus2024.md"
    focus.write_text(FOCUS, encoding="utf-8")
    return focus, Upstream([ref_item(i) for i in range(450)], [cit_item(i) for i in range(3)])


def go(vault, focus, upstream, more=False):
    summary = run_explore(vault, focus, "k", upstream, pacer=Pacer(sleep=lambda s: None), more=more)
    assert summary.ok, summary.message
    return summary


def explore_files(vault: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted((vault / "_explore").glob("*.md"))}


def digest(files: dict[str, bytes]) -> dict[str, str]:
    return {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}


def stub_ids(vault: Path) -> dict[str, str]:
    return {
        p.name: read_stub_ids(p.read_text(encoding="utf-8")).s2_id
        for p in (vault / "_explore").glob("*.md")
        if p.name not in ("_focus.md", "_trail.md")
    }


def ranked_refs(upstream):
    lean = [
        Neighbor(
            r["citedPaper"]["paperId"], None, None, (), None, None, r["citedPaper"]["citationCount"],
            r["isInfluential"], None, None, "reference",
        )
        for r in upstream.refs
    ]  # fmt: skip
    return [n.s2_id for n in rank_neighbors(lean)]


def listed_refs(vault: Path) -> list[str]:
    """s2_ids listed under References in _focus.md, in order."""
    text = (vault / "_explore" / "_focus.md").read_text(encoding="utf-8")
    block = text.split("## References")[1].split("## Citations")[0]
    by_stem = {Path(n).stem: i for n, i in stub_ids(vault).items()}
    return [by_stem[stem] for stem in re.findall(r"^- \[\[(.+)\]\]$", block, re.M)]


def test_more_adds_the_next_200_in_rank_order(tmp_path):
    focus, upstream = make(tmp_path)
    go(tmp_path, focus, upstream)
    go(tmp_path, focus, upstream, more=True)
    ids = stub_ids(tmp_path)
    refs = [i for i in ids.values() if i.startswith("R")]
    assert len(refs) == 400 and len(set(refs)) == 400
    assert set(refs) == set(ranked_refs(upstream)[:400])
    assert sum(1 for i in ids.values() if i.startswith("C")) == 3
    text = (tmp_path / "_explore" / "_focus.md").read_text(encoding="utf-8")
    assert "showing 400 of 450 references" in text and "showing 3 of 3 citations" in text
    assert listed_refs(tmp_path) == ranked_refs(upstream)[:400]


def test_existing_stubs_and_trail_are_byte_identical_after_more(tmp_path):
    focus, upstream = make(tmp_path)
    go(tmp_path, focus, upstream)
    before = digest(explore_files(tmp_path))
    go(tmp_path, focus, upstream, more=True)
    after = digest(explore_files(tmp_path))
    for name, value in before.items():
        if name != "_focus.md":
            assert after[name] == value, name
    assert len(after) > len(before)


def test_more_fetches_details_only_for_the_new_stubs(tmp_path):
    focus, upstream = make(tmp_path)
    go(tmp_path, focus, upstream)
    upstream.posted.clear()
    go(tmp_path, focus, upstream, more=True)
    assert set(upstream.posted) == set(ranked_refs(upstream)[200:400])


def test_third_more_writes_the_rest_and_fourth_changes_nothing(tmp_path):
    focus, upstream = make(tmp_path)
    go(tmp_path, focus, upstream)
    go(tmp_path, focus, upstream, more=True)
    go(tmp_path, focus, upstream, more=True)
    assert len([i for i in stub_ids(tmp_path).values() if i.startswith("R")]) == 450
    assert "showing 450 of 450 references" in (tmp_path / "_explore" / "_focus.md").read_text(encoding="utf-8")
    before = explore_files(tmp_path)
    upstream.posted.clear()
    go(tmp_path, focus, upstream, more=True)
    assert explore_files(tmp_path) == before
    assert upstream.posted == []


def test_more_for_a_different_note_exits_1_and_changes_nothing(tmp_path, monkeypatch, capsys):
    focus, upstream = make(tmp_path)
    go(tmp_path, focus, upstream)
    other = tmp_path / "@other.md"
    other.write_text(FOCUS.replace("focus2024", "other").replace(DOI, "10.1016/other"), encoding="utf-8")
    before = {p.name: p.read_bytes() for p in tmp_path.rglob("*.md")}
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("S2_API_KEY", "k")
    code = main(["explore", "--vault", str(tmp_path), str(other), "--more"], transport=upstream, sleep=lambda s: None)
    assert code == 1
    assert "focus" in capsys.readouterr().err.lower()
    assert {p.name: p.read_bytes() for p in tmp_path.rglob("*.md")} == before


def test_more_without_a_previous_explore_exits_1(tmp_path, monkeypatch):
    focus, upstream = make(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("S2_API_KEY", "k")
    code = main(["explore", "--vault", str(tmp_path), str(focus), "--more"], transport=upstream, sleep=lambda s: None)
    assert code == 1
    assert not (tmp_path / "_explore").exists()


def test_failed_fetch_during_more_leaves_every_file_alone_and_exits_1(tmp_path, monkeypatch):
    focus, upstream = make(tmp_path)
    go(tmp_path, focus, upstream)
    before = {p.name: p.read_bytes() for p in tmp_path.rglob("*.md")}
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("S2_API_KEY", "k")
    broken = Upstream([], [], fail=True)
    code = main(["explore", "--vault", str(tmp_path), str(focus), "--more"], transport=broken, sleep=lambda s: None)
    assert code == 1
    assert {p.name: p.read_bytes() for p in tmp_path.rglob("*.md")} == before


def test_parser_accepts_more_flag():
    args = build_parser().parse_args(["explore", "--vault", "V", "n.md", "--more"])
    assert args.more is True
    assert build_parser().parse_args(["explore", "n.md"]).more is False
