"""Paper-source coordination built on the frozen Collector 1.0 contract."""

from .domain import (
    PAPER_SOURCE_IDS,
    authors_from_snapshot,
    author_name_matches,
    covered_authors,
    deduplicate_paper_items,
    normalize_author_name,
    normalize_doi,
    paper_identity_key,
)
from .service import AbstractResolution, AbstractResolver, PaperCollectionBatch, PaperCollectorCoordinator
from .arxiv import ArxivCollector, ArxivQuery
from .collectors import CrossrefCollector, SemanticScholarCollector
from .http import (
    PaperHttpRuntime,
    UpstreamLimiter,
    UpstreamPolicy,
    default_paper_http_runtime,
    install_default_paper_http_runtime,
)
from .module import register, unregister
from .projection import project_today_payload

__all__ = [
    "PAPER_SOURCE_IDS",
    "AbstractResolution",
    "AbstractResolver",
    "PaperCollectionBatch",
    "PaperCollectorCoordinator",
    "PaperHttpRuntime",
    "UpstreamLimiter",
    "UpstreamPolicy",
    "ArxivCollector",
    "ArxivQuery",
    "CrossrefCollector",
    "SemanticScholarCollector",
    "author_name_matches",
    "authors_from_snapshot",
    "covered_authors",
    "deduplicate_paper_items",
    "normalize_author_name",
    "normalize_doi",
    "paper_identity_key",
    "project_today_payload",
    "register",
    "unregister",
    "default_paper_http_runtime",
    "install_default_paper_http_runtime",
]
