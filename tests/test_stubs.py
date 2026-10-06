"""Behaviour of the stub note text and stub id reading (pure domain)."""

from lit_vault_tools.domain.doi import PaperIds
from lit_vault_tools.domain.neighbors import Neighbor
from lit_vault_tools.domain.stubs import read_stub_ids, render_stub


def make(**kw) -> Neighbor:
    base = dict(
        s2_id="abc123", doi="10.1234/Loops.5", title="Dislocation loops in tungsten",
        authors=("Ann Jones", "Bo Li"), year=2019, venue="J. Nucl. Mater.",
        citation_count=42, is_influential=True, tldr="Loops grow under dose.",
        abstract="We study loops.", relation="citation",
    )
    base.update(kw)
    return Neighbor(**base)


FULL = """\
---
type: stub
s2_id: abc123
doi: "10.1234/loops.5"
relation: citation
---
# Dislocation loops in tungsten

**Authors:** Ann Jones, Bo Li
**Year:** 2019
**Venue:** J. Nucl. Mater.
**Citations:** 42
**Influential:** yes

**TL;DR:** Loops grow under dose.

## Abstract

We study loops.

**DOI:** [10.1234/loops.5](https://doi.org/10.1234/loops.5)
"""


def test_full_neighbor_renders_exact_text():
    assert render_stub(make()) == FULL


def test_no_wikilinks_even_with_brackets_in_text():
    text = render_stub(make(authors=("[[Ann]] Jones",), title="On [[links]] and ]]", abstract="[[x]]"))
    assert "[[" not in text
    assert "Ann" in text and "links" in text


def test_missing_optional_sections_omitted_and_no_none():
    text = render_stub(make(abstract=None, tldr=None, venue=None, doi=None, year=None,
                            citation_count=None, is_influential=False))
    assert "None" not in text and "null" not in text
    assert "doi:" not in text and "DOI" not in text
    assert "Abstract" not in text and "TL;DR" not in text and "Venue" not in text
    assert "**Influential:** no" in text


def test_ids_round_trip_and_deterministic():
    n = make()
    assert read_stub_ids(render_stub(n)) == PaperIds(doi="10.1234/loops.5", s2_id="abc123")
    assert render_stub(n) == render_stub(n)
    assert read_stub_ids(render_stub(make(doi=None))) == PaperIds(doi=None, s2_id="abc123")
