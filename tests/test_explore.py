"""explore end to end: temp vault with real notes, fake transport replaying the real S2 shapes."""

import dataclasses
import json
import re
from pathlib import Path

from lit_vault_tools.cli import build_parser, main
from lit_vault_tools.clients.http import ClientError, HttpResponse
from lit_vault_tools.clients.semantic_scholar import Pacer
from lit_vault_tools.commands.explore import run_explore
from lit_vault_tools.config import STUB_CAP_PER_LIST
from lit_vault_tools.domain.frontmatter import read_scalar, split_note
from lit_vault_tools.domain.neighbors import Neighbor, rank_neighbors
from lit_vault_tools.domain.stubs import read_stub_ids, render_stub

FIXTURES = Path(__file__).parent / "fixtures"
REF_ITEM = json.loads((FIXTURES / "s2_references_page1.json").read_text(encoding="utf-8"))["data"][0]
CIT_ITEM = json.loads((FIXTURES / "s2_citations_page1.json").read_text(encoding="utf-8"))["data"][0]
BATCH_ENTRY = next(e for e in json.loads((FIXTURES / "s2_batch.json").read_text(encoding="utf-8")) if e)
FOCUS_DOI = "10.1016/j.matdes.2024.112730"
FOCUS = f"---\ntype: paper\ncitekey: focus2024\ndoi: {FOCUS_DOI}\n---\nMy own notes.\n"


def item(kind: str, prefix: str, i: int) -> dict:
    """A real-shaped neighbor entry with a unique id; counts/influence vary deterministically."""
    template = REF_ITEM if kind == "citedPaper" else CIT_ITEM
    inner_key = kind
    paper = dict(template[inner_key])
    paper["paperId"] = f"{prefix}{i:04d}"
    paper["title"] = f"Paper {prefix}{i}"
    paper["citationCount"] = (i * 37) % 101
    paper["externalIds"] = {"DOI": f"10.9999/{prefix.lower()}{i}"}
    return {"isInfluential": i % 17 == 0, inner_key: paper}


def details_entry(pid: str) -> dict:
    return {
        **BATCH_ENTRY,
        "paperId": pid,
        "abstract": f"Abstract of {pid}",
        "tldr": {"model": "tldr@v2", "text": f"TLDR of {pid}"},
        "authors": [{"authorId": "1", "name": f"Author of {pid}"}],
        "venue": "Test Venue",
    }


class Upstream:
    """Fake Semantic Scholar: serves pages of `refs`/`cits`, optionally failing on the nth request."""

    def __init__(self, refs, cits, page_size=1000, fail_on_request=None):
        self.refs, self.cits, self.page_size = refs, cits, page_size
        self.fail_on_request = fail_on_request
        self.requests = []
        self.posted_ids = []

    def __call__(self, method, url, headers, body):
        self.requests.append((method, url))
        if self.fail_on_request and len(self.requests) == self.fail_on_request:
            raise ClientError(500, url)
        if method == "POST":
            ids = json.loads(body)["ids"]
            self.posted_ids.extend(ids)
            return HttpResponse(200, json.dumps([details_entry(i) for i in ids]).encode())
        items = self.refs if "/references?" in url else self.cits
        offset = int(re.search(r"offset=(\d+)", url).group(1))
        page = items[offset : offset + self.page_size]
        payload = {"offset": offset, "data": page}
        if offset + self.page_size < len(items):
            payload["next"] = offset + self.page_size
        return HttpResponse(200, json.dumps(payload).encode())


def pacer():
    return Pacer(sleep=lambda s: None)


def make_vault(tmp_path: Path) -> tuple[Path, Path]:
    focus = tmp_path / "@focus2024.md"
    focus.write_text(FOCUS, encoding="utf-8")
    (tmp_path / "other.md").write_text("---\ntype: paper\ndoi: 10.1/x\n---\nbody\n", encoding="utf-8")
    return tmp_path, focus


def tree(root: Path, include_explore=False) -> dict[str, bytes]:
    return {
        str(p.relative_to(root)): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file() and (include_explore or "_explore" not in p.relative_to(root).parts)
    }


def lean(item_, relation, key):
    paper = item_[key]
    return Neighbor(
        s2_id=paper["paperId"],
        doi=paper["externalIds"]["DOI"],
        title=paper["title"],
        authors=(),
        year=paper["year"],
        venue=None,
        citation_count=paper["citationCount"],
        is_influential=item_["isInfluential"],
        tldr=None,
        abstract=None,
        relation=relation,
    )


def test_cap_ranking_focus_file_and_details_for_selected_only(tmp_path):
    vault, focus = make_vault(tmp_path)
    refs = [item("citedPaper", "R", i) for i in range(450)]
    cits = [item("citingPaper", "C", i) for i in range(3)]
    before = tree(vault)
    upstream = Upstream(refs, cits)
    summary = run_explore(vault, focus, "k", upstream, pacer=pacer())
    assert summary.ok
    explore = vault / "_explore"
    stub_files = [p for p in explore.glob("*.md") if p.name not in ("_focus.md", "_trail.md")]
    stubs = {p: read_stub_ids(p.read_text(encoding="utf-8")).s2_id for p in stub_files}
    assert len(stubs) == STUB_CAP_PER_LIST + 3
    assert sum(1 for i in stubs.values() if i.startswith("R")) == 200

    ranked = rank_neighbors([lean(r, "reference", "citedPaper") for r in refs])[:200]
    assert {i for i in stubs.values() if i.startswith("R")} == {n.s2_id for n in ranked}

    # _focus.md: type, focus link, rank order and the showing lines
    focus_text = (explore / "_focus.md").read_text(encoding="utf-8")
    parts = split_note(focus_text)
    assert read_scalar(parts, "type") == "focus"
    assert read_scalar(parts, "focus") == "[[@focus2024]]"
    assert "showing 200 of 450 references" in focus_text and "showing 3 of 3 citations" in focus_text
    by_stem = {p.stem: sid for p, sid in stubs.items()}
    references_block = focus_text.split("## References")[1].split("## Citations")[0]
    listed = [by_stem[m] for m in re.findall(r"^- \[\[(.+)\]\]$", references_block, re.M)]
    assert listed == [n.s2_id for n in ranked]

    # stub text = render_stub(lean neighbor + batch details); details fetched only for the 203 selected
    lean_by_id = {
        **{r["citedPaper"]["paperId"]: lean(r, "reference", "citedPaper") for r in refs},
        **{c["citingPaper"]["paperId"]: lean(c, "citation", "citingPaper") for c in cits},
    }
    for path, sid in stubs.items():
        expected = dataclasses.replace(
            lean_by_id[sid],
            abstract=f"Abstract of {sid}",
            tldr=f"TLDR of {sid}",
            authors=(f"Author of {sid}",),
            venue="Test Venue",
        )
        assert path.read_text(encoding="utf-8") == render_stub(expected)
    assert sorted(upstream.posted_ids) == sorted(stubs.values())
    assert len(upstream.posted_ids) == 203

    # saved notes untouched
    assert tree(vault) == before


def test_explore_dir_is_created_wiped_and_outside_is_untouched(tmp_path):
    vault, focus = make_vault(tmp_path)
    (vault / "_explore").mkdir()
    (vault / "_explore" / "old stub.md").write_text("old", encoding="utf-8")
    before = tree(vault)
    run_explore(vault, focus, "k", Upstream([item("citedPaper", "R", 1)], []), pacer=pacer())
    assert not (vault / "_explore" / "old stub.md").exists()
    assert tree(vault) == before


def test_missing_explore_dir_is_created(tmp_path):
    vault, focus = make_vault(tmp_path)
    run_explore(vault, focus, "k", Upstream([], []), pacer=pacer())
    assert (vault / "_explore" / "_focus.md").is_file()


def test_failure_leaves_previous_explore_files_byte_identical(tmp_path):
    vault, focus = make_vault(tmp_path)
    (vault / "_explore").mkdir()
    (vault / "_explore" / "previous.md").write_text("previous focus stub", encoding="utf-8")
    (vault / "_explore" / "_focus.md").write_text("previous focus", encoding="utf-8")
    before = tree(vault, include_explore=True)
    refs = [item("citedPaper", "R", i) for i in range(30)]
    upstream = Upstream(refs, [], page_size=10, fail_on_request=2)
    summary = run_explore(vault, focus, "k", upstream, pacer=pacer())
    assert not summary.ok and summary.message
    assert tree(vault, include_explore=True) == before


def test_main_exits_1_on_upstream_failure_and_leaves_explore_alone(tmp_path, monkeypatch):
    vault, focus = make_vault(tmp_path)
    (vault / "_explore").mkdir()
    (vault / "_explore" / "previous.md").write_text("previous", encoding="utf-8")
    before = tree(vault, include_explore=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("S2_API_KEY", "k")
    upstream = Upstream([item("citedPaper", "R", i) for i in range(30)], [], page_size=10, fail_on_request=2)
    code = main(["explore", "--vault", str(vault), str(focus)], transport=upstream, sleep=lambda s: None)
    assert code == 1
    assert tree(vault, include_explore=True) == before


def test_main_success_exit_code_0(tmp_path, monkeypatch):
    vault, focus = make_vault(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("S2_API_KEY", "k")
    upstream = Upstream([item("citedPaper", "R", 1)], [item("citingPaper", "C", 1)])
    assert main(["explore", "--vault", str(vault), str(focus)], transport=upstream, sleep=lambda s: None) == 0
    assert len(list((vault / "_explore").glob("*.md"))) == 2 + 2  # two stubs, _focus.md and _trail.md


def test_focus_note_without_doi_exits_1_and_changes_nothing(tmp_path, monkeypatch, capsys):
    vault = tmp_path
    focus = vault / "nodoi.md"
    focus.write_text("---\ntype: paper\ncitekey: x\n---\nbody\n", encoding="utf-8")
    (vault / "_explore").mkdir()
    (vault / "_explore" / "keep.md").write_text("keep", encoding="utf-8")
    before = tree(vault, include_explore=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("S2_API_KEY", "k")
    upstream = Upstream([], [])
    assert main(["explore", "--vault", str(vault), str(focus)], transport=upstream, sleep=lambda s: None) == 1
    assert "doi" in capsys.readouterr().err.lower()
    assert upstream.requests == []
    assert tree(vault, include_explore=True) == before


def test_missing_s2_key_exits_2_without_calling_transport(tmp_path, monkeypatch, capsys):
    vault, focus = make_vault(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("S2_API_KEY", raising=False)
    upstream = Upstream([], [])
    assert main(["explore", "--vault", str(vault), str(focus)], transport=upstream, sleep=lambda s: None) == 2
    assert capsys.readouterr().err
    assert upstream.requests == []


def test_s2_key_can_come_from_env_file(tmp_path, monkeypatch):
    vault, focus = make_vault(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("S2_API_KEY", raising=False)
    (tmp_path / ".env").write_text("S2_API_KEY=from-file\n", encoding="utf-8")
    seen = []

    class Spy(Upstream):
        def __call__(self, method, url, headers, body):
            seen.append(headers.get("x-api-key"))
            return super().__call__(method, url, headers, body)

    assert main(["explore", "--vault", str(vault), str(focus)], transport=Spy([], []), sleep=lambda s: None) == 0
    assert set(seen) == {"from-file"}


def test_parser_accepts_explore(tmp_path):
    args = build_parser().parse_args(["explore", "--vault", "V", "n.md"])
    assert (args.command, args.vault, args.note) == ("explore", "V", "n.md")


def test_hidden_references_are_reported_not_shown_as_empty(tmp_path):
    vault, focus = make_vault(tmp_path)

    class Hidden(Upstream):
        def __call__(self, method, url, headers, body):
            if "/references?" in url:
                self.requests.append((method, url))
                return HttpResponse(200, json.dumps({"data": None}).encode())
            return super().__call__(method, url, headers, body)

    summary = run_explore(vault, focus, "k", Hidden([], [item("citingPaper", "C", 1)]), pacer=pacer())
    assert summary.ok and summary.references_hidden
    text = (vault / "_explore" / "_focus.md").read_text(encoding="utf-8")
    assert "hidden" in text.lower() and "showing 0 of 0 references" not in text
    assert "showing 1 of 1 citations" in text
