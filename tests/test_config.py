"""The config constants are the contract other modules import; pin their values."""

from lit_vault_tools import config


def test_enrichment_keys_are_the_owned_keys_in_context_md():
    assert config.ENRICHMENT_KEYS == (
        "openalex_id",
        "s2_id",
        "oa_status",
        "institutions",
        "countries",
        "authors",
        "subfield",
        "refs",
        "cited_by",
        "enrich_status",
        "enriched_on",
    )


def test_explore_tunables():
    assert config.EXPLORE_DIR == "_explore"
    assert config.STUB_CAP_PER_LIST == 200
    assert config.TRAIL_LENGTH == 3
