"""Frontmatter regions: byte-preserving read and enrichment write.

Notes are our own file format, so the tests build them by hand; no files, no fakes.
"""

import datetime

import pytest

from lit_vault_tools.config import ENRICHMENT_KEYS
from lit_vault_tools.domain.frontmatter import (
    apply_enrichment,
    read_list,
    read_scalar,
    split_note,
)

MARKER = "# ---- enrichment-script-owned ----"

NORMAL = (
    "---\n"
    "type: paper\n"
    "citekey: smith2021ion\n"
    "title: Ion things\n"
    "doi: 10.1016/j.jnucmat.2021.000000\n"
    "abstract: |\n"
    "  First line of the abstract.\n"
    "  Second line: with a colon.\n"
    "---\n"
    "My own notes.\n"
    "\n"
    "More of my notes.\n"
)
NORMAL_FM = NORMAL.split("---\n")[1]
NORMAL_BODY = "My own notes.\n\nMore of my notes.\n"

ROUND_TRIPS = {
    "normal": NORMAL,
    "no frontmatter": "Just a body.\nSecond line.\n",
    "empty body": "---\ntype: paper\n---\n",
    "no trailing newline": "---\ntype: paper\n---\nbody",
    "body with own rules": "---\ntype: paper\n---\nintro\n---\nnot frontmatter\n---\n",
    "crlf": "---\r\ntype: paper\r\ndoi: 10.1/x\r\n---\r\nbody line\r\nsecond\r\n",
    "unclosed frontmatter": "---\ntype: paper\nno closing rule\n",
    "empty": "",
}


@pytest.mark.parametrize("text", ROUND_TRIPS.values(), ids=ROUND_TRIPS.keys())
def test_split_then_render_is_byte_identical(text):
    assert split_note(text).render() == text


def test_body_is_returned_byte_for_byte():
    assert split_note(NORMAL).body == NORMAL_BODY
    assert split_note(ROUND_TRIPS["body with own rules"]).body == "intro\n---\nnot frontmatter\n---\n"
    assert split_note(ROUND_TRIPS["crlf"]).body == "body line\r\nsecond\r\n"
    assert split_note(ROUND_TRIPS["no frontmatter"]).body == "Just a body.\nSecond line.\n"


@pytest.mark.parametrize(
    "line",
    [
        "doi: 10.1016/x",
        'doi: "10.1016/x"',
        "doi: '10.1016/x'",
        "doi: 10.1016/x  # note",
        'doi: "10.1016/x"  # note',
    ],
)
def test_read_scalar_strips_quotes_and_trailing_comment(line):
    parts = split_note(f"---\ntype: paper\n{line}\n---\nbody\n")
    assert read_scalar(parts, "doi") == "10.1016/x"


def test_read_scalar_absent_key_is_none():
    assert read_scalar(split_note(NORMAL), "openalex_id") is None


def test_read_scalar_ignores_indented_lines_and_body():
    text = "---\nabstract: |\n  doi: 10.9/inside\n---\ndoi: 10.8/body\n"
    assert read_scalar(split_note(text), "doi") is None


def test_read_scalar_on_note_without_frontmatter():
    assert read_scalar(split_note("doi: 10.1/x\n"), "doi") is None


def test_read_list():
    parts = split_note('---\nrefs: ["[[A]]", "[[B]]"]\nempty: []\n---\n')
    assert read_list(parts, "refs") == ["[[A]]", "[[B]]"]
    assert read_list(parts, "empty") == []
    assert read_list(parts, "absent") == []


def test_read_list_handles_commas_inside_quotes_and_block_form():
    text = "---\nrefs: [\"[[A, B]]\", '[[C]]']\nauthors:\n  - \"[[X]]\"\n  - \"[[Y]]\"\n---\n"
    parts = split_note(text)
    assert read_list(parts, "refs") == ["[[A, B]]", "[[C]]"]
    assert read_list(parts, "authors") == ["[[X]]", "[[Y]]"]


VALUES = {
    "openalex_id": "W1234567890",
    "oa_status": "green",
    "countries": ["US", "DE"],
    "authors": ["[[Jane Doe]]"],
    "refs": [],
    "enrich_status": "ok",
}
TODAY = datetime.date(2026, 10, 6)


def test_apply_enrichment_preserves_other_lines_order_and_body():
    out = split_note(apply_enrichment(split_note(NORMAL), VALUES, TODAY).render())
    assert out.body == NORMAL_BODY
    fm = "".join(out.lines)
    assert fm.startswith(NORMAL_FM)
    assert fm.startswith(NORMAL_FM)
    expected = [
        MARKER,
        "openalex_id: W1234567890",
        "oa_status: green",
        'countries: ["US", "DE"]',
        'authors: ["[[Jane Doe]]"]',
        "refs: []",
        "enrich_status: ok",
        "enriched_on: 2026-10-06",
    ]
    assert fm[len(NORMAL_FM) :].splitlines() == expected


def test_apply_enrichment_writes_keys_in_enrichment_keys_order():
    shuffled = dict(reversed(list(VALUES.items())))
    out = apply_enrichment(split_note(NORMAL), shuffled, TODAY).render()
    keys = [line.split(":")[0] for line in out.splitlines() if line.split(":")[0] in ENRICHMENT_KEYS]
    assert keys == sorted(keys, key=ENRICHMENT_KEYS.index)
    assert keys[-1] == "enriched_on"


def test_apply_enrichment_omits_none_values():
    out = apply_enrichment(split_note(NORMAL), {"openalex_id": "W1", "s2_id": None}, TODAY).render()
    assert "s2_id" not in out
    assert "openalex_id: W1\n" in out


def test_none_removes_an_existing_owned_key():
    first = apply_enrichment(split_note(NORMAL), {"openalex_id": "W1", "s2_id": "abc"}, TODAY)
    second = apply_enrichment(first, {"s2_id": None}, TODAY)
    assert read_scalar(second, "s2_id") is None
    assert read_scalar(second, "openalex_id") == "W1"


@pytest.mark.parametrize("key", ["citekey", "title", "doi", "type", "not_a_key"])
def test_apply_enrichment_rejects_keys_it_does_not_own(key):
    parts = split_note(NORMAL)
    with pytest.raises(ValueError):
        apply_enrichment(parts, {"openalex_id": "W1", key: "x"}, TODAY)
    assert parts == split_note(NORMAL)
    assert parts.render() == NORMAL


def test_apply_enrichment_rejects_caller_supplied_enriched_on():
    with pytest.raises(ValueError):
        apply_enrichment(split_note(NORMAL), {"enriched_on": "1999-01-01"}, TODAY)


def test_apply_enrichment_twice_equals_once():
    once = apply_enrichment(split_note(NORMAL), VALUES, TODAY)
    twice = apply_enrichment(split_note(once.render()), VALUES, TODAY)
    assert twice.render() == once.render()


def test_enriched_on_set_to_today_with_no_existing_block():
    out = apply_enrichment(split_note(NORMAL), VALUES, TODAY)
    assert read_scalar(out, "enriched_on") == "2026-10-06"


def test_enriched_on_kept_when_values_identical():
    first = apply_enrichment(split_note(NORMAL), VALUES, datetime.date(2026, 1, 1))
    later = apply_enrichment(split_note(first.render()), VALUES, datetime.date(2026, 12, 31))
    assert read_scalar(later, "enriched_on") == "2026-01-01"
    assert later.render() == first.render()


def test_enriched_on_bumped_when_any_value_changed():
    first = apply_enrichment(split_note(NORMAL), VALUES, datetime.date(2026, 1, 1))
    changed = {**VALUES, "countries": ["US"]}
    later = apply_enrichment(first, changed, datetime.date(2026, 12, 31))
    assert read_scalar(later, "enriched_on") == "2026-12-31"
    assert read_list(later, "countries") == ["US"]


def test_enriched_on_bumped_when_a_key_is_added_or_removed():
    first = apply_enrichment(split_note(NORMAL), VALUES, datetime.date(2026, 1, 1))
    added = apply_enrichment(first, {"s2_id": "abc"}, datetime.date(2026, 2, 2))
    assert read_scalar(added, "enriched_on") == "2026-02-02"
    removed = apply_enrichment(added, {"s2_id": None}, datetime.date(2026, 3, 3))
    assert read_scalar(removed, "enriched_on") == "2026-03-03"


def test_existing_block_is_rewritten_in_place_not_duplicated():
    text = NORMAL.replace("---\nMy own", f"{MARKER}\nopenalex_id: W0\ncountries: [US]\n---\nMy own")
    out = apply_enrichment(split_note(text), {"openalex_id": "W9"}, TODAY).render()
    assert out.count(MARKER) == 1
    assert out.count("openalex_id:") == 1
    assert "openalex_id: W9\n" in out
    assert "W0" not in out
    assert "countries" in out


def test_unchanged_note_is_returned_byte_for_byte():
    text = NORMAL.replace(
        "---\nMy own",
        f"{MARKER}\nopenalex_id: W0\ncountries: [US]\nenriched_on: 2026-01-01\n---\nMy own",
    )
    out = apply_enrichment(split_note(text), {"openalex_id": "W0", "countries": ["US"]}, TODAY)
    assert out.render() == text


def test_multiline_owned_value_is_replaced_whole():
    text = 'type: paper\nrefs:\n  - "[[A]]"\n  - "[[B]]"\ndoi: 10.1/x\n'
    out = apply_enrichment(split_note(f"---\n{text}---\nbody\n"), {"refs": ["[[C]]"]}, TODAY).render()
    assert "[[A]]" not in out
    assert 'refs: ["[[C]]"]\n' in out
    assert "doi: 10.1/x\n" in out
    assert out.endswith("---\nbody\n")


def test_crlf_note_stays_all_crlf():
    text = "---\r\ntype: paper\r\ndoi: 10.1/x\r\n---\r\nbody\r\n"
    out = apply_enrichment(split_note(text), VALUES, TODAY).render()
    assert out.count("\n") == out.count("\r\n")
    assert out.endswith("---\r\nbody\r\n")
    assert out.startswith("---\r\ntype: paper\r\ndoi: 10.1/x\r\n")


def test_value_needing_quotes_round_trips():
    out = apply_enrichment(split_note(NORMAL), {"oa_status": "a: b # c"}, TODAY)
    assert read_scalar(out, "oa_status") == "a: b # c"


def test_note_without_frontmatter_gets_a_block_and_keeps_its_body():
    out = apply_enrichment(split_note("Just a body.\n"), {"openalex_id": "W1"}, TODAY).render()
    assert out == f"---\n{MARKER}\nopenalex_id: W1\nenriched_on: 2026-10-06\n---\nJust a body.\n"


def test_set_key_line_replaces_in_place_and_keeps_everything_else():
    from lit_vault_tools.domain.frontmatter import set_key_line, split_note

    text = '---\r\ntype: author\r\naliases: ["a"]\r\nnote: |\r\n  keep\r\n---\r\nbody\r\n'
    out = set_key_line(split_note(text), "aliases", '["a", "b"]').render()
    assert out == '---\r\ntype: author\r\naliases: ["a", "b"]\r\nnote: |\r\n  keep\r\n---\r\nbody\r\n'


def test_set_key_line_appends_missing_key_and_drops_block_continuation():
    from lit_vault_tools.domain.frontmatter import set_key_line, split_note

    appended = set_key_line(split_note("---\ntype: institution\n---\nmine\n"), "location", "1.5,2.5").render()
    assert appended == "---\ntype: institution\nlocation: 1.5,2.5\n---\nmine\n"
    block = set_key_line(split_note("---\naliases:\n  - old\ntype: x\n---\n"), "aliases", '["new"]').render()
    assert block == '---\naliases: ["new"]\ntype: x\n---\n'
