"""DOI normalization and paper matching: pure functions, no fakes, no files."""

import dataclasses

import pytest

from lit_vault_tools.domain.doi import PaperIds, find_paper, normalize_doi

CANONICAL = "10.1016/j.jnucmat.2021.000000"

VALID_FORMS = [
    "https://doi.org/10.1016/J.JNUCMAT.2021.000000",
    "http://dx.doi.org/10.1016/J.JNUCMAT.2021.000000",
    "doi:10.1016/J.JNUCMAT.2021.000000",
    " 10.1016/j.jnucmat.2021.000000 ",
]


@pytest.mark.parametrize("raw", VALID_FORMS)
def test_normalize_doi_strips_prefix_whitespace_and_case(raw):
    assert normalize_doi(raw) == CANONICAL


@pytest.mark.parametrize("raw", [None, "", "   ", "not a doi"])
def test_normalize_doi_rejects_non_dois(raw):
    assert normalize_doi(raw) is None


@pytest.mark.parametrize("raw", VALID_FORMS)
def test_normalize_doi_is_idempotent(raw):
    once = normalize_doi(raw)
    assert normalize_doi(once) == once


def test_paper_ids_default_to_none_and_are_frozen():
    ids = PaperIds()
    assert (ids.doi, ids.openalex_id, ids.s2_id) == (None, None, None)
    with pytest.raises(dataclasses.FrozenInstanceError):
        ids.doi = "10.1/x"


def test_find_paper_matches_doi_despite_case_and_url_prefix():
    candidates = [
        PaperIds(doi="10.1/other"),
        PaperIds(doi="https://doi.org/10.1016/J.JNUCMAT.2021.000000"),
    ]
    assert find_paper(PaperIds(doi=CANONICAL), candidates) == 1


def test_find_paper_matches_on_openalex_id_alone():
    candidates = [PaperIds(openalex_id="W1"), PaperIds(openalex_id="W2", doi="10.1/a")]
    assert find_paper(PaperIds(openalex_id="W2"), candidates) == 1


def test_find_paper_matches_on_s2_id_alone():
    candidates = [PaperIds(s2_id="aaa"), PaperIds(s2_id="bbb")]
    assert find_paper(PaperIds(s2_id="bbb"), candidates) == 1


def test_find_paper_returns_first_of_several_matches():
    candidates = [PaperIds(openalex_id="W1"), PaperIds(openalex_id="W1")]
    assert find_paper(PaperIds(openalex_id="W1"), candidates) == 0


def test_find_paper_returns_none_when_nothing_matches():
    candidates = [PaperIds(doi="10.1/a", openalex_id="W1", s2_id="x")]
    assert find_paper(PaperIds(doi="10.1/b", openalex_id="W2", s2_id="y"), candidates) is None


def test_find_paper_missing_id_never_equals_missing_id():
    assert find_paper(PaperIds(), [PaperIds()]) is None
    assert find_paper(PaperIds(), [PaperIds(doi="10.1/a")]) is None


def test_find_paper_with_no_candidates():
    assert find_paper(PaperIds(doi="10.1/a"), []) is None
