"""Deprecated arXiv compatibility facade.

The implementation and process-wide HTTP coordination are owned by
``features.papers``.  Keep this module import-compatible for legacy scripts.
"""

from features.papers.arxiv import (
    ARXIV_API,
    ARXIV_CACHE_DIR,
    ARXIV_CACHE_TTL_SECONDS,
    ARXIV_MAX_RETRIES,
    ARXIV_MIN_INTERVAL,
    ARXIV_TRUST_ENV,
    ArxivCollector,
    ArxivQuery,
    Paper,
    clear_arxiv_failures,
    fetch_arxiv_papers,
    get_arxiv_failures,
)

__all__ = [
    "ARXIV_API",
    "ARXIV_CACHE_DIR",
    "ARXIV_CACHE_TTL_SECONDS",
    "ARXIV_MAX_RETRIES",
    "ARXIV_MIN_INTERVAL",
    "ARXIV_TRUST_ENV",
    "ArxivCollector",
    "ArxivQuery",
    "Paper",
    "clear_arxiv_failures",
    "fetch_arxiv_papers",
    "get_arxiv_failures",
]
