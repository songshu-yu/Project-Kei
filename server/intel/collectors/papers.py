"""Deprecated paper-source compatibility facade.

Collector 1.0 implementations, legacy adapters, and shared HTTP coordination
are owned by ``features.papers``.  This module intentionally contains no
upstream business rules or limiter state.
"""

from features.papers.collectors import (
    CROSSREF_BASE,
    JOURNAL_ALIASES,
    OPTICS_JOURNALS,
    SS_BASE,
    SS_MIN_INTERVAL,
    USER_AGENT,
    CrossrefCollector,
    PaperItem,
    SemanticScholarCollector,
    enrich_missing_abstracts,
    fetch_abstract_for_doi_or_url,
    fetch_all_journals,
    fetch_journal_latest_crossref,
    fetch_recent_crossref_for_authors,
    print_papers,
    search_by_author_semantic_scholar,
    search_corresponding_papers,
)

__all__ = [
    "CROSSREF_BASE",
    "JOURNAL_ALIASES",
    "OPTICS_JOURNALS",
    "SS_BASE",
    "SS_MIN_INTERVAL",
    "USER_AGENT",
    "CrossrefCollector",
    "PaperItem",
    "SemanticScholarCollector",
    "enrich_missing_abstracts",
    "fetch_abstract_for_doi_or_url",
    "fetch_all_journals",
    "fetch_journal_latest_crossref",
    "fetch_recent_crossref_for_authors",
    "print_papers",
    "search_by_author_semantic_scholar",
    "search_corresponding_papers",
]
