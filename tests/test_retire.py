"""Stub retirement: a stub whose paper is now saved is deleted, and its links point at the real note."""

import datetime
import json
from pathlib import Path

from lit_vault_tools.clients.http import HttpResponse
from lit_vault_tools.clients.semantic_scholar import Pacer
from lit_vault_tools.commands.enrich import run_enrich
from lit_vault_tools.commands.explore import run_explore
from lit_vault_tools.vault.retire import retire_stubs

FIXTURES = Path(__file__).parent / "fixtures"
REF_ITEM = json.loads((FIXTURES / "s2_references_page1.json").read_text(encoding="utf-8"))["data"][0]
BATCH_ENTRY = next(e for e in json.loads((FIXTURES / "s2_batch.json").read_text(encoding="utf-8")) if e)


def put(vault: Path, rel: str, text: str) -> Path:
    path = vault / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    return path


def saved(doi: str | None = None, s2_id: str | None = None) -> str:
    lines = ["type: paper"]
    if doi:
        lines.append(f"doi: {doi}")
    if s2_id:
        lines.append(f"s2_id: {s2_id}")
    return "---\n" + "\n".join(lines) + "\n---\nMy notes.\n"


def stub(s2_id: str, doi: str | None = None) -> str:
    doi_line = f"doi: {doi}\n" if doi else ""
    return f"---\ntype: stub\ns2_id: {s2_id}\n{doi_line}relation: reference\n---\n# Title\n"


FOCUS = (
    '---\ntype: focus\nfocus: "[[@focus]]"\n---\n\n## References\n\n'
    "- [[Jones 2019 - A stub]]\n- [[Other 2020 - Keep]]\n"
)
TRAIL = "---\ntype: trail\n---\n\n1. [[@focus]]\n2. [[Jones 2019 - A stub]]\n"


def tree(vault: Path) -> dict[str, bytes]:
    return {str(p.relative_to(vault)): p.read_bytes() for p in sorted(vault.rglob("*")) if p.is_file()}


def test_doi_match_ignoring_case_and_prefix_retires_and_repoints_links(tmp_path):
    saved_note = put(tmp_path, "@jones2019.md", saved(doi="10.1016/abc.123"))
    put(tmp_path, "_explore/Jones 2019 - A stub.md", stub("S1", doi="https://DOI.org/10.1016/ABC.123"))
    put(tmp_path, "_explore/Other 2020 - Keep.md", stub("S2", doi="10.1000/other"))
    put(tmp_path, "_explore/_focus.md", FOCUS)
    put(tmp_path, "_explore/_trail.md", TRAIL)
    changing = ("A stub", "_focus", "_trail")
    untouched = {k: v for k, v in tree(tmp_path).items() if not any(name in k for name in changing)}
    assert retire_stubs(tmp_path) == ["Jones 2019 - A stub"]
    assert not (tmp_path / "_explore" / "Jones 2019 - A stub.md").exists()
    assert "- [[@jones2019]]" in (tmp_path / "_explore" / "_focus.md").read_text(encoding="utf-8")
    assert "[[A stub" not in (tmp_path / "_explore" / "_focus.md").read_text(encoding="utf-8")
    assert "2. [[@jones2019]]" in (tmp_path / "_explore" / "_trail.md").read_text(encoding="utf-8")
    after = tree(tmp_path)
    assert {k: after[k] for k in untouched} == untouched
    assert saved_note.exists()


def test_unmatched_stub_stays_and_s2_id_match_retires(tmp_path):
    put(tmp_path, "@a.md", saved(s2_id="SAME"))
    put(tmp_path, "_explore/by id.md", stub("SAME"))
    put(tmp_path, "_explore/no match.md", stub("OTHER", doi="10.1000/zzz"))
    assert retire_stubs(tmp_path) == ["by id"]
    assert not (tmp_path / "_explore" / "by id.md").exists()
    assert (tmp_path / "_explore" / "no match.md").exists()


def test_never_deletes_outside_explore_or_any_saved_note(tmp_path):
    put(tmp_path, "@a.md", saved(doi="10.1000/same"))
    outside = put(tmp_path, "Papers/x.md", stub("S9", doi="10.1000/same"))
    before = tree(tmp_path)
    saved_paths = sorted(p for p in tmp_path.rglob("*.md") if "type: paper" in p.read_text(encoding="utf-8"))
    assert retire_stubs(tmp_path) == []
    assert outside.exists()
    assert tree(tmp_path) == before
    assert sorted(p for p in tmp_path.rglob("*.md") if "type: paper" in p.read_text(encoding="utf-8")) == saved_paths


def test_only_stubs_directly_under_explore_are_considered(tmp_path):
    put(tmp_path, "@a.md", saved(doi="10.1000/same"))
    deep = put(tmp_path, "_explore/sub/deep.md", stub("S9", doi="10.1000/same"))
    assert retire_stubs(tmp_path) == []
    assert deep.exists()


def test_a_non_stub_in_explore_is_left_alone(tmp_path):
    put(tmp_path, "@a.md", saved(doi="10.1000/same"))
    other = put(tmp_path, "_explore/_focus.md", FOCUS.replace("A stub", "x"))
    before = other.read_bytes()
    assert retire_stubs(tmp_path) == []
    assert other.read_bytes() == before


def test_trail_does_not_end_up_listing_the_same_note_twice(tmp_path):
    put(tmp_path, "@jones2019.md", saved(doi="10.1000/same"))
    put(tmp_path, "_explore/Jones 2019 - A stub.md", stub("S1", doi="10.1000/same"))
    trail = "---\ntype: trail\n---\n\n1. [[@jones2019]]\n2. [[Jones 2019 - A stub]]\n3. [[@z]]\n"
    put(tmp_path, "_explore/_trail.md", trail)
    retire_stubs(tmp_path)
    text = (tmp_path / "_explore" / "_trail.md").read_text(encoding="utf-8")
    assert text.endswith("1. [[@jones2019]]\n2. [[@z]]\n")


def test_via_explore_a_saved_neighbor_has_no_stub_and_focus_links_the_saved_note(tmp_path):
    focus = put(tmp_path, "@focus.md", saved(doi="10.1016/focus"))
    put(tmp_path, "@neighbor.md", saved(doi="10.9999/r1"))
    refs = []
    for i in range(3):
        paper = dict(REF_ITEM["citedPaper"], paperId=f"R{i}", title=f"Paper R{i}", citationCount=10 - i)
        paper["externalIds"] = {"DOI": f"10.9999/r{i}"}
        refs.append({"isInfluential": False, "citedPaper": paper})

    def upstream(method, url, headers, body):
        if method == "POST":
            ids = json.loads(body)["ids"]
            return HttpResponse(200, json.dumps([{**BATCH_ENTRY, "paperId": i} for i in ids]).encode())
        data = refs if "/references?" in url else []
        return HttpResponse(200, json.dumps({"offset": 0, "data": data}).encode())

    summary = run_explore(tmp_path, focus, "k", upstream, pacer=Pacer(sleep=lambda s: None))
    assert summary.ok
    texts = [p.read_text(encoding="utf-8") for p in (tmp_path / "_explore").glob("*.md")]
    assert not any("s2_id: R1" in t for t in texts)
    assert sum(1 for t in texts if "s2_id: R" in t) == 2
    focus_text = (tmp_path / "_explore" / "_focus.md").read_text(encoding="utf-8")
    assert "- [[@neighbor]]" in focus_text
    assert "@neighbor.md" in {p.name for p in tmp_path.glob("*.md")}


def test_via_enrich_a_newly_saved_paper_retires_its_stub_and_rerun_changes_nothing(tmp_path):
    put(tmp_path, "_explore/Jones 2019 - A stub.md", stub("S1", doi="10.1000/new"))
    put(tmp_path, "_explore/_focus.md", FOCUS)
    put(tmp_path, "_explore/_trail.md", TRAIL)
    put(tmp_path, "@jones2019.md", saved(doi="10.1000/new"))

    def not_found(method, url, headers, body):
        return HttpResponse(404, b"{}")

    run_enrich(tmp_path, None, "k", not_found, datetime.date(2026, 10, 1))
    assert not (tmp_path / "_explore" / "Jones 2019 - A stub.md").exists()
    assert "- [[@jones2019]]" in (tmp_path / "_explore" / "_focus.md").read_text(encoding="utf-8")
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in tmp_path.rglob("*.md")}
    assert retire_stubs(tmp_path) == []
    assert {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in tmp_path.rglob("*.md")} == before
