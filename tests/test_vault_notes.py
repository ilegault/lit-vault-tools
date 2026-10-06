"""Vault note I/O against a real temporary vault: real files, no fakes."""

import os
from pathlib import Path

import pytest

from lit_vault_tools.vault.notes import scan_saved_notes, write_note


def make(vault: Path, rel: str, data: bytes) -> Path:
    path = vault / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def paper(extra: str = "", eol: str = "\n") -> bytes:
    extra = extra.replace("\n", eol)
    return f"---{eol}type: paper{eol}{extra}---{eol}My notes.{eol}".encode()


def snapshot(vault: Path) -> dict[str, bytes]:
    return {
        p.relative_to(vault).as_posix(): p.read_bytes()
        for p in sorted(vault.rglob("*"))
        if p.is_file()
    }


def test_scan_returns_only_paper_notes_recursively_sorted(tmp_path):
    make(tmp_path, "b.md", paper())
    make(tmp_path, "sub/deeper/a.md", paper())
    make(tmp_path, "a.md", paper())
    make(tmp_path, "author.md", b"---\ntype: author\n---\n")
    make(tmp_path, "stub.md", b"---\ntype: stub\n---\n")
    make(tmp_path, "plain.md", b"no frontmatter\n")
    make(tmp_path, "_explore/p.md", paper())
    make(tmp_path, ".obsidian/p.md", paper())
    make(tmp_path, "sub/.hidden/p.md", paper())
    make(tmp_path, "paper.txt", paper())
    found = [n.path for n in scan_saved_notes(tmp_path)]
    assert found == [
        tmp_path / "a.md",
        tmp_path / "b.md",
        tmp_path / "sub" / "deeper" / "a.md",
    ]


def test_scan_reads_normalized_ids_and_text(tmp_path):
    data = paper("doi: https://doi.org/10.1016/ABC\nopenalex_id: W123\ns2_id: abcdef\n")
    make(tmp_path, "n.md", data)
    (note,) = scan_saved_notes(tmp_path)
    assert note.ids.doi == "10.1016/abc"
    assert note.ids.openalex_id == "W123"
    assert note.ids.s2_id == "abcdef"
    assert note.text == data.decode()


def test_scan_missing_ids_are_none(tmp_path):
    make(tmp_path, "n.md", paper())
    (note,) = scan_saved_notes(tmp_path)
    assert (note.ids.doi, note.ids.openalex_id, note.ids.s2_id) == (None, None, None)


def test_crlf_note_round_trips_byte_identical(tmp_path):
    data = paper("doi: 10.1/x\n", eol="\r\n")
    path = make(tmp_path, "n.md", data)
    (note,) = scan_saved_notes(tmp_path)
    assert "\r\n" in note.text
    assert write_note(path, note.text) is False
    assert path.read_bytes() == data


def test_crlf_text_written_has_no_newline_translation(tmp_path):
    path = make(tmp_path, "n.md", paper())
    new = "---\r\ntype: paper\r\n---\r\nbody\r\n"
    assert write_note(path, new) is True
    assert path.read_bytes() == new.encode()


def test_write_unchanged_returns_false_and_leaves_mtime(tmp_path):
    path = make(tmp_path, "n.md", paper())
    os.utime(path, ns=(1_000_000_000, 1_000_000_000))
    before = path.stat().st_mtime_ns
    assert write_note(path, path.read_bytes().decode()) is False
    assert path.stat().st_mtime_ns == before


def test_write_changed_returns_true_and_bytes_match(tmp_path):
    path = make(tmp_path, "n.md", paper())
    new = "---\ntype: paper\ndoi: 10.1/x\n---\nMy notes.\nüï\n"
    assert write_note(path, new) is True
    assert path.read_bytes() == new.encode("utf-8")


def test_write_leaves_no_stray_files(tmp_path):
    path = make(tmp_path, "sub/n.md", paper())
    make(tmp_path, "other.md", paper())
    before = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*"))
    write_note(path, "---\ntype: paper\n---\nchanged\n")
    after = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*"))
    assert after == before


def test_failure_between_temp_write_and_replace_keeps_original(tmp_path, monkeypatch):
    data = paper()
    path = make(tmp_path, "n.md", data)
    before = sorted(p.name for p in tmp_path.iterdir())

    def boom(*args, **kwargs):
        raise OSError("injected")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError, match="injected"):
        write_note(path, "---\ntype: paper\n---\nchanged\n")
    assert path.read_bytes() == data
    assert sorted(p.name for p in tmp_path.iterdir()) == before


def test_scan_then_rewrite_each_note_changes_nothing(tmp_path):
    make(tmp_path, "a.md", paper("doi: 10.1/a\n", eol="\r\n"))
    make(tmp_path, "sub/b.md", paper("title: üï\n"))
    make(tmp_path, "author.md", b"---\ntype: author\n---\n")
    make(tmp_path, "_explore/s.md", b"---\ntype: stub\n---\n")
    before = snapshot(tmp_path)
    for note in scan_saved_notes(tmp_path):
        assert write_note(note.path, note.text) is False
    assert snapshot(tmp_path) == before
