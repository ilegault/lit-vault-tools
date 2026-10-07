"""`_explore/` helper: the only place anything is deleted, and only inside `_explore/`."""

from pathlib import Path

from lit_vault_tools.vault.explore_dir import wipe_explore, write_stub


def snapshot(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def test_wipe_creates_a_missing_explore_dir(tmp_path):
    wipe_explore(tmp_path)
    assert (tmp_path / "_explore").is_dir()


def test_wipe_removes_everything_inside_and_nothing_outside(tmp_path):
    (tmp_path / "_explore" / "sub").mkdir(parents=True)
    (tmp_path / "_explore" / "old stub.md").write_text("old", encoding="utf-8")
    (tmp_path / "_explore" / "sub" / "deep.md").write_text("deep", encoding="utf-8")
    (tmp_path / "paper.md").write_text("mine", encoding="utf-8")
    (tmp_path / "Authors").mkdir()
    (tmp_path / "Authors" / "A.md").write_text("a", encoding="utf-8")
    outside = snapshot(tmp_path)
    outside = {k: v for k, v in outside.items() if not k.startswith("_explore")}
    wipe_explore(tmp_path)
    assert list((tmp_path / "_explore").iterdir()) == []
    assert snapshot(tmp_path) == outside


def test_write_stub_writes_inside_explore_and_returns_path(tmp_path):
    wipe_explore(tmp_path)
    path = write_stub(tmp_path, "Jones 2019 - Title", "text\n")
    assert path == tmp_path / "_explore" / "Jones 2019 - Title.md"
    assert path.read_bytes() == b"text\n"
