"""Explore trail and stubs as focus: fake S2 transport returning different neighbor lists per paper ref."""

import json
import re
from pathlib import Path
from urllib.parse import unquote

from lit_vault_tools.clients.http import ClientError, HttpResponse
from lit_vault_tools.clients.semantic_scholar import Pacer
from lit_vault_tools.commands.explore import run_explore
from lit_vault_tools.domain.frontmatter import read_scalar, split_note
from lit_vault_tools.domain.stubs import read_stub_ids
from lit_vault_tools.vault.explore_dir import wipe_explore

FIXTURES = Path(__file__).parent / "fixtures"
REF_ITEM = json.loads((FIXTURES / "s2_references_page1.json").read_text(encoding="utf-8"))["data"][0]
CIT_ITEM = json.loads((FIXTURES / "s2_citations_page1.json").read_text(encoding="utf-8"))["data"][0]
BATCH_ENTRY = next(e for e in json.loads((FIXTURES / "s2_batch.json").read_text(encoding="utf-8")) if e)
FOCUS_DOI = "10.1016/j.matdes.2024.112730"
A_NOTE = f"---\ntype: paper\ncitekey: focusA\ndoi: {FOCUS_DOI}\n---\nMy own notes on A.\n"


def ref(pid: str, count: int = 5) -> dict:
    paper = dict(REF_ITEM["citedPaper"], paperId=pid, title=f"Title {pid}", citationCount=count)
    paper["externalIds"] = {"DOI": f"10.9999/{pid.lower()}"}
    return {"isInfluential": False, "citedPaper": paper}


def cit(pid: str, count: int = 5) -> dict:
    paper = dict(CIT_ITEM["citingPaper"], paperId=pid, title=f"Title {pid}", citationCount=count)
    paper["externalIds"] = {"DOI": f"10.9999/{pid.lower()}"}
    return {"isInfluential": False, "citingPaper": paper}


class Upstream:
    """`lists` maps a paper ref (`DOI:...` or an s2 id) to (references, citations)."""

    def __init__(self, lists, fail=False):
        self.lists = lists
        self.fail = fail
        self.requested = []

    def __call__(self, method, url, headers, body):
        if self.fail:
            raise ClientError(500, url)
        if method == "POST":
            ids = json.loads(body)["ids"]
            entries = [{**BATCH_ENTRY, "paperId": i, "abstract": f"Abstract {i}"} for i in ids]
            return HttpResponse(200, json.dumps(entries).encode())
        match = re.search(r"/paper/(.+)/(references|citations)\?", url)
        paper_ref, kind = unquote(match.group(1)), match.group(2)
        self.requested.append((paper_ref, kind))
        refs, cits = self.lists[paper_ref]
        return HttpResponse(200, json.dumps({"offset": 0, "data": refs if kind == "references" else cits}).encode())


def explore(vault, focus, upstream, **kwargs):
    summary = run_explore(vault, focus, "k", upstream, pacer=Pacer(sleep=lambda s: None), **kwargs)
    assert summary.ok, summary.message
    return summary


def stub_for(vault: Path, s2_id: str) -> Path:
    for path in (vault / "_explore").glob("*.md"):
        if read_stub_ids(path.read_text(encoding="utf-8")).s2_id == s2_id:
            return path
    raise AssertionError(f"no stub with s2_id {s2_id}")


def trail(vault: Path) -> list[str]:
    text = (vault / "_explore" / "_trail.md").read_text(encoding="utf-8")
    return re.findall(r"^\d+\. \[\[(.+)\]\]$", text, re.M)


def chain_lists():
    """A (saved) -> B1 -> C1 -> D1 -> E1; every paper also has an unrelated neighbor."""
    return {
        f"DOI:{FOCUS_DOI}": ([ref("B1"), ref("X1")], []),
        "B1": ([ref("C1"), ref("X2")], []),
        "C1": ([ref("D1"), ref("X3")], [cit("B1")]),
        "D1": ([ref("E1"), ref("X4")], []),
        "E1": ([ref("X5")], []),
    }


def setup(tmp_path):
    a = tmp_path / "@focusA.md"
    a.write_text(A_NOTE, encoding="utf-8")
    return a, Upstream(chain_lists())


def test_four_foci_keep_three_newest_first_and_saved_note_untouched(tmp_path):
    a, upstream = setup(tmp_path)
    before_a = a.read_bytes()
    explore(tmp_path, a, upstream)
    assert trail(tmp_path) == ["@focusA"]
    explore(tmp_path, stub_for(tmp_path, "B1"), upstream)
    explore(tmp_path, stub_for(tmp_path, "C1"), upstream)
    b_stem, c_stem = stub_for(tmp_path, "B1").stem, stub_for(tmp_path, "C1").stem
    assert trail(tmp_path) == [c_stem, b_stem, "@focusA"]
    explore(tmp_path, stub_for(tmp_path, "D1"), upstream, trail_length=3)
    d_stem = stub_for(tmp_path, "D1").stem
    assert trail(tmp_path) == [d_stem, c_stem, b_stem]
    assert a.read_bytes() == before_a  # a saved note pushed out of the trail is left alone


def test_a_stub_pushed_out_of_the_trail_is_deleted(tmp_path):
    a, upstream = setup(tmp_path)
    explore(tmp_path, a, upstream)
    for pid in ("B1", "C1", "D1"):
        explore(tmp_path, stub_for(tmp_path, pid), upstream)
    b_path = stub_for(tmp_path, "B1")
    assert not b_path.exists() or b_path.stem in trail(tmp_path)
    explore(tmp_path, stub_for(tmp_path, "E1"), upstream)
    assert [p for p in (tmp_path / "_explore").glob("*.md") if read_stub_ids(p.read_text("utf-8")).s2_id == "B1"] == []


def test_trail_stubs_survive_the_wipe_and_other_neighbors_do_not(tmp_path):
    a, upstream = setup(tmp_path)
    explore(tmp_path, a, upstream)
    b_path = stub_for(tmp_path, "B1")
    x1_path = stub_for(tmp_path, "X1")
    b_bytes = b_path.read_bytes()
    explore(tmp_path, b_path, upstream)
    assert b_path.read_bytes() == b_bytes
    assert not x1_path.exists()
    explore(tmp_path, stub_for(tmp_path, "C1"), upstream)
    assert b_path.read_bytes() == b_bytes  # still in the trail, so still preserved


def test_a_neighbor_that_is_a_trail_stub_is_not_duplicated(tmp_path):
    a, upstream = setup(tmp_path)
    explore(tmp_path, a, upstream)
    explore(tmp_path, stub_for(tmp_path, "B1"), upstream)
    b_stem = stub_for(tmp_path, "B1").stem
    explore(tmp_path, stub_for(tmp_path, "C1"), upstream)  # C1's citations include B1
    matching = [p for p in (tmp_path / "_explore").glob("*.md") if read_stub_ids(p.read_text("utf-8")).s2_id == "B1"]
    assert [p.stem for p in matching] == [b_stem]
    assert f"- [[{b_stem}]]" in (tmp_path / "_explore" / "_focus.md").read_text(encoding="utf-8")


def test_reexploring_a_note_in_the_trail_moves_it_to_the_front_and_refetches(tmp_path):
    a, upstream = setup(tmp_path)
    explore(tmp_path, a, upstream)
    explore(tmp_path, stub_for(tmp_path, "B1"), upstream)
    b_stem = stub_for(tmp_path, "B1").stem
    upstream.requested.clear()
    explore(tmp_path, a, upstream)
    assert trail(tmp_path) == ["@focusA", b_stem]
    assert (f"DOI:{FOCUS_DOI}", "references") in upstream.requested


def test_exploring_a_stub_resolves_by_s2_id_and_focus_links_to_the_stub(tmp_path):
    a, upstream = setup(tmp_path)
    explore(tmp_path, a, upstream)
    b_path = stub_for(tmp_path, "B1")
    upstream.requested.clear()
    explore(tmp_path, b_path, upstream)
    assert ("B1", "references") in upstream.requested
    focus_text = (tmp_path / "_explore" / "_focus.md").read_text(encoding="utf-8")
    assert read_scalar(split_note(focus_text), "focus") == f"[[{b_path.stem}]]"


def test_a_saved_note_focus_never_creates_a_stub(tmp_path):
    a, upstream = setup(tmp_path)
    explore(tmp_path, a, upstream)
    names = {p.stem for p in (tmp_path / "_explore").glob("*.md")}
    assert "@focusA" not in names and len(names) == 2 + 2  # B1, X1 stubs + _focus + _trail


def test_failed_run_keeps_the_trail_as_it_was(tmp_path):
    a, upstream = setup(tmp_path)
    explore(tmp_path, a, upstream)
    before = (tmp_path / "_explore" / "_trail.md").read_bytes()
    broken = Upstream({}, fail=True)
    summary = run_explore(tmp_path, stub_for(tmp_path, "B1"), "k", broken, pacer=Pacer(sleep=lambda s: None))
    assert not summary.ok
    assert (tmp_path / "_explore" / "_trail.md").read_bytes() == before


def test_wipe_explore_keep_preserves_named_stubs_only(tmp_path):
    (tmp_path / "_explore").mkdir()
    for name in ("keep me", "drop me", "_focus"):
        (tmp_path / "_explore" / f"{name}.md").write_text(name, encoding="utf-8")
    wipe_explore(tmp_path, keep={"keep me"})
    assert sorted(p.name for p in (tmp_path / "_explore").iterdir()) == ["keep me.md"]
