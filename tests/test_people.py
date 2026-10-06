"""Author / institution / subfield naming and rendering: pure functions."""

import pytest

from lit_vault_tools.domain.frontmatter import read_list, read_scalar, split_note
from lit_vault_tools.domain.people import (
    AuthorRef,
    InstitutionRef,
    assign_author_filenames,
    institution_location,
    merge_aliases,
    render_author_note,
    render_institution_note,
    render_subfield_note,
    sanitize_filename,
)


def test_sanitize_replaces_forbidden_and_trims():
    assert sanitize_filename("A/B: C?") == "A-B- C-"
    for ch in '\\/:*?"<>|':
        assert ch not in sanitize_filename(f"a{ch}b")
    assert sanitize_filename("Jane Doe. . ") == "Jane Doe"


@pytest.mark.parametrize("raw", ["", "   ", "...", ". ."])
def test_sanitize_empty_becomes_unnamed(raw):
    assert sanitize_filename(raw) == "Unnamed"


def _jane(i):
    return AuthorRef(openalex_id=f"A{i}", display_name="Jane Doe")


def test_collision_uses_institution_then_counter():
    seen = [
        (_jane(1), "Oak Ridge National Laboratory"),
        (_jane(2), "Oak Ridge National Laboratory"),
        (_jane(3), "Oak Ridge National Laboratory"),
        (_jane(4), "Oak Ridge National Laboratory"),
    ]
    out = assign_author_filenames(seen, {})
    assert out["A1"] == "Jane Doe"
    assert out["A2"] == "Jane Doe (Oak Ridge National Laboratory)"
    assert out["A3"] == "Jane Doe (Oak Ridge National Laboratory) (2)"
    assert out["A4"] == "Jane Doe (Oak Ridge National Laboratory) (3)"


def test_collision_without_institution_gets_counter():
    out = assign_author_filenames([(_jane(1), None), (_jane(2), None)], {})
    assert out == {"A1": "Jane Doe", "A2": "Jane Doe (2)"}


def test_existing_filenames_are_never_changed_and_order_independent():
    seen = [(_jane(1), "ORNL"), (_jane(2), "MIT"), (_jane(3), "ANL")]
    first = assign_author_filenames(seen, {})
    again = assign_author_filenames(list(reversed(seen)), dict(first))
    assert again == first


def test_existing_is_not_mutated_and_blocks_new_names():
    existing = {"A1": "Jane Doe"}
    snapshot = dict(existing)
    out = assign_author_filenames([(_jane(2), "MIT")], existing)
    assert existing == snapshot
    assert out["A1"] == "Jane Doe"
    assert out["A2"] == "Jane Doe (MIT)"


def test_collision_is_case_insensitive_and_names_are_sanitized():
    a = AuthorRef("A1", "jane doe")
    b = AuthorRef("A2", "Jane Doe")
    out = assign_author_filenames([(a, None), (b, "M/I:T")], {})
    assert out["A1"] == "jane doe"
    assert out["A2"] == "Jane Doe (M-I-T)"


def test_empty_name_uses_unnamed():
    out = assign_author_filenames([(AuthorRef("A1", ""), None)], {})
    assert out["A1"] == "Unnamed"


def test_merge_aliases_order_dedupe_and_idempotent():
    merged = merge_aliases(["J. Doe", "Jane A. Doe"], ["J. A. Doe", "J. Doe", "Jane Doe", "J. A. Doe"], "Jane Doe")
    assert merged == ["J. Doe", "Jane A. Doe", "J. A. Doe"]
    assert merge_aliases(merged, ["J. A. Doe", "J. Doe", "Jane Doe"], "Jane Doe") == merged


def test_merge_aliases_keeps_existing_even_if_duplicated_removes_display_name():
    assert merge_aliases(["x", "x", "Jane Doe"], [], "Jane Doe") == ["x"]


def test_location_text():
    assert institution_location(35.9, -84.3) == "35.9,-84.3"


@pytest.mark.parametrize("lat,lng", [(None, 1.0), (1.0, None), (None, None), (0, 0), (0.0, 0.0)])
def test_location_unknown_is_none(lat, lng):
    assert institution_location(lat, lng) is None


def test_location_one_zero_axis_is_kept():
    assert institution_location(0.0, 10.5) == "0.0,10.5"


def test_render_author_note():
    text = render_author_note(AuthorRef("A1", "Jane Doe"), ["J. Doe", "Jane D."])
    parts = split_note(text)
    assert read_scalar(parts, "type") == "author"
    assert read_scalar(parts, "openalex_id") == "A1"
    assert read_list(parts, "aliases") == ["J. Doe", "Jane D."]
    assert parts.body == ""
    assert text == render_author_note(AuthorRef("A1", "Jane Doe"), ["J. Doe", "Jane D."])


def test_render_author_note_no_aliases():
    parts = split_note(render_author_note(AuthorRef("A1", "Jane Doe"), []))
    assert read_list(parts, "aliases") == []


def test_render_institution_note_full():
    inst = InstitutionRef("I1", "Oak Ridge National Laboratory", "https://ror.org/01qz5mb56", "US", "government")
    text = render_institution_note(inst, institution_location(35.9, -84.3))
    parts = split_note(text)
    assert read_scalar(parts, "type") == "institution"
    assert read_scalar(parts, "ror") == "https://ror.org/01qz5mb56"
    assert read_scalar(parts, "country") == "US"
    assert read_scalar(parts, "institution_type") == "government"
    assert read_scalar(parts, "openalex_id") == "I1"
    assert read_scalar(parts, "location") == "35.9,-84.3"
    assert text == render_institution_note(inst, "35.9,-84.3")


def test_render_institution_note_without_location_has_no_zero_zero():
    inst = InstitutionRef("I1", "X", None, None, None)
    text = render_institution_note(inst, institution_location(0, 0))
    assert "location" not in text
    assert "0,0" not in text
    assert read_scalar(split_note(text), "type") == "institution"


def test_render_subfield_note():
    text = render_subfield_note("Nuclear Energy and Engineering")
    parts = split_note(text)
    assert read_scalar(parts, "type") == "subfield"
    assert text == render_subfield_note("Nuclear Energy and Engineering")
