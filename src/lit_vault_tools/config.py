"""Constants and tunables. No I/O, no imports from the rest of the package.

WHY THIS EXISTS
---------------
Every other layer imports from here, so a tunable lives in exactly one place.
`ENRICHMENT_KEYS` is the ownership boundary from CONTEXT.md: the frontmatter
keys the enrichment script owns. Anything not listed is Zotero's or the
developer's, and the script must never write it.
"""

ENRICHMENT_KEYS: tuple[str, ...] = (
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

EXPLORE_DIR = "_explore"
AUTHORS_DIR = "Authors"
INSTITUTIONS_DIR = "Institutions"
SUBFIELDS_DIR = "Subfields"
STUB_CAP_PER_LIST = 200
TRAIL_LENGTH = 3
STUB_TITLE_MAX_CHARS = 40

# Semantic Scholar: nominal 1 req/s proved tight in practice (decision 18).
S2_MIN_INTERVAL_S = 1.5
S2_BACKOFF_S: tuple[int, ...] = (5, 10, 20, 40)
S2_PAGE_LIMIT = 1000
S2_BATCH_SIZE = 500
