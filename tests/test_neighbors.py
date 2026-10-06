"""Behaviour of explore's neighbor ranking and stub naming (pure domain)."""

import random

from lit_vault_tools.config import STUB_TITLE_MAX_CHARS
from lit_vault_tools.domain.neighbors import Neighbor, rank_neighbors, stub_filename


def make(s2_id="a", **kw) -> Neighbor:
    base = dict(
        s2_id=s2_id, doi=None, title="Some title", authors=("Ann Jones",), year=2019,
        venue=None, citation_count=0, is_influential=False, tldr=None, abstract=None,
        relation="reference",
    )
    base.update(kw)
    return Neighbor(**base)


def test_rank_influential_then_citations_then_id():
    items = [
        make("d", citation_count=5),
        make("c", citation_count=50),
        make("b", citation_count=1, is_influential=True),
        make("a", citation_count=5),
    ]
    assert [n.s2_id for n in rank_neighbors(items)] == ["b", "c", "a", "d"]


def test_rank_none_counts_as_zero_and_input_unmutated():
    items = [make("b", citation_count=None), make("a", citation_count=0), make("c", citation_count=1)]
    before = list(items)
    assert [n.s2_id for n in rank_neighbors(items)] == ["c", "a", "b"]
    assert items == before


def test_rank_is_order_independent():
    items = [make(str(i), citation_count=i % 3, is_influential=i % 4 == 0) for i in range(30)]
    expected = rank_neighbors(items)
    for seed in range(5):
        shuffled = list(items)
        random.Random(seed).shuffle(shuffled)
        assert rank_neighbors(shuffled) == expected


def test_filename_basic_and_truncation():
    n = make(title="Dislocation loops in irradiated tungsten alloys under stress")
    cut = n.title[:STUB_TITLE_MAX_CHARS].rstrip()
    assert stub_filename(n, set()) == f"Jones 2019 - {cut}…"


def test_filename_short_title_has_no_ellipsis():
    exact = "x" * STUB_TITLE_MAX_CHARS
    assert stub_filename(make(title=exact), set()) == f"Jones 2019 - {exact}"
    assert stub_filename(make(title="Short"), set()) == "Jones 2019 - Short"


def test_filename_missing_year_and_authors():
    name = stub_filename(make(year=None, authors=()), set())
    assert name == "Unknown n.d. - Some title"


def test_filename_uses_last_word_of_first_author():
    assert stub_filename(make(authors=("Maria de la Cruz", "Bo Li")), set()).startswith("Cruz 2019")


def test_filename_forbidden_characters_replaced():
    name = stub_filename(make(title="A/B: C?"), set())
    assert not set(name) & set('/:?')
    assert name.startswith("Jones 2019 - A-B- C-")


def test_filename_collisions_case_insensitive_and_taken_unmutated():
    base = stub_filename(make(), set())
    taken = {base.upper()}
    assert stub_filename(make(), taken) == f"{base} (2)"
    taken.add(f"{base} (2)".lower())
    assert stub_filename(make(), taken) == f"{base} (3)"
    assert len(taken) == 2
