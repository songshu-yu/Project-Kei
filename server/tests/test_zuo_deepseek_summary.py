"""Summarize Chao Zuo's papers for a month with DeepSeek.

Run from the server directory:
    python test_zuo_deepseek_summary.py

Optional:
    python test_zuo_deepseek_summary.py --month 2026-06
    python test_zuo_deepseek_summary.py --max-papers 8

Environment variables:
    DEEPSEEK_API_KEY=...
or:
    LLM_API_KEY=...
    LLM_BASE_URL=https://api.deepseek.com/v1
    LLM_MODEL=deepseek-chat
"""
from __future__ import annotations

import _path_setup  # noqa: F401
import argparse
import asyncio
import html
import os
import re
import sys
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

import httpx

from intel.collectors.papers import (
    OPTICS_JOURNALS,
    PaperItem,
    search_by_author_semantic_scholar,
    search_corresponding_papers,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = PROJECT_ROOT / ".env"
USER_AGENT = "ProjectKei/0.1 abstract-enrichment"
CROSSREF_BASE = "https://api.crossref.org"


def configure_utf8_stdio() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def load_dotenv_if_exists(path: Path = ENV_FILE) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def month_key(value: str) -> str:
    return (value or "").strip()[:7]


def is_in_month(paper: PaperItem, month: str) -> bool:
    return month_key(paper.published) == month


def clean(value: str, max_len: int | None = None) -> str:
    value = " ".join((value or "").split())
    if max_len and len(value) > max_len:
        return value[: max_len - 3].rstrip() + "..."
    return value


def normalize_abstract(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(r"^\s*abstract\s*[:.\-]?\s*", "", value, flags=re.IGNORECASE)
    return value


def is_better_abstract(candidate: str, current: str) -> bool:
    candidate = normalize_abstract(candidate)
    current = normalize_abstract(current)
    if len(candidate) < 120:
        return False
    if not current:
        return True
    return len(candidate) >= len(current) + 80


class MetaAbstractParser(HTMLParser):
    ABSTRACT_KEYS = {
        "citation_abstract",
        "dc.description",
        "description",
        "og:description",
        "twitter:description",
    }

    def __init__(self) -> None:
        super().__init__()
        self.candidates: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "meta":
            return
        attr_map = {k.lower(): (v or "") for k, v in attrs}
        key = attr_map.get("name") or attr_map.get("property")
        content = attr_map.get("content", "")
        if key and key.lower() in self.ABSTRACT_KEYS and content:
            self.candidates.append((key.lower(), normalize_abstract(content)))


async def fetch_crossref_abstract(client: httpx.AsyncClient, doi: str) -> str:
    if not doi:
        return ""
    try:
        resp = await client.get(f"{CROSSREF_BASE}/works/{doi}")
        resp.raise_for_status()
        abstract = resp.json().get("message", {}).get("abstract", "")
        return normalize_abstract(abstract)
    except Exception as exc:
        print(f"[Enrich] Crossref failed for {doi}: {type(exc).__name__}: {exc}")
        return ""


async def fetch_page_meta_abstract(client: httpx.AsyncClient, url: str) -> str:
    if not url:
        return ""
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        parser = MetaAbstractParser()
        parser.feed(resp.text[:500_000])
    except Exception as exc:
        print(f"[Enrich] Page failed for {url}: {type(exc).__name__}: {exc}")
        return ""

    if not parser.candidates:
        return ""

    priority = {
        "citation_abstract": 0,
        "dc.description": 1,
        "description": 2,
        "og:description": 3,
        "twitter:description": 4,
    }
    parser.candidates.sort(key=lambda item: (priority.get(item[0], 99), -len(item[1])))
    return parser.candidates[0][1]


async def enrich_abstracts(papers: list[PaperItem]) -> None:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/json,application/vnd.crossref-api-message+json,*/*",
    }
    async with httpx.AsyncClient(
        timeout=30.0,
        headers=headers,
        follow_redirects=True,
        trust_env=True,
    ) as client:
        for idx, paper in enumerate(papers, 1):
            current = normalize_abstract(paper.abstract)
            print(f"[Enrich] [{idx}/{len(papers)}] {paper.title[:80]}")

            crossref_abstract = await fetch_crossref_abstract(client, paper.doi)
            if is_better_abstract(crossref_abstract, current):
                paper.abstract = crossref_abstract
                print(f"[Enrich]   Crossref abstract: {len(current)} -> {len(paper.abstract)} chars")
                continue

            urls = []
            if paper.doi:
                urls.append(f"https://doi.org/{paper.doi}")
            if paper.url and paper.url not in urls:
                urls.append(paper.url)

            for url in urls:
                page_abstract = await fetch_page_meta_abstract(client, url)
                if is_better_abstract(page_abstract, current):
                    paper.abstract = page_abstract
                    print(f"[Enrich]   Page meta abstract: {len(current)} -> {len(paper.abstract)} chars")
                    break
            else:
                print(f"[Enrich]   No better abstract found ({len(current)} chars)")


def paper_for_prompt(paper: PaperItem, idx: int, abstract_chars: int | None) -> str:
    authors = ", ".join(paper.authors[:8])
    if len(paper.authors) > 8:
        authors += f", ... ({len(paper.authors)} authors)"
    abstract = clean(paper.abstract, abstract_chars) or "No abstract available."
    return "\n".join(
        [
            f"[{idx}] {clean(paper.title)}",
            f"Journal: {clean(paper.journal) or 'Unknown'}",
            f"Published: {paper.published or 'Unknown'}",
            f"Authors: {authors or 'Unknown'}",
            f"DOI: {paper.doi or 'N/A'}",
            f"URL: {paper.url or 'N/A'}",
            f"Abstract: {abstract}",
        ]
    )


def build_prompt(author: str, month: str, papers: list[PaperItem], abstract_chars: int | None) -> str:
    paper_blocks = "\n\n".join(paper_for_prompt(p, i, abstract_chars) for i, p in enumerate(papers, 1))
    return f"""请用中文总结 {author} 在 {month} 的论文动态。

请基于下面的论文标题、期刊、作者和摘要，输出：
1. 一段 150-250 字总体总结
2. 每篇论文的要点列表，每篇 2-3 个 bullet
3. 如果摘要缺失，请明确说明“摘要缺失，仅基于标题和元数据判断”
4. 最后给出“值得关注的方向”3 条

不要编造摘要里没有的信息。

论文列表：

{paper_blocks}
"""


async def summarize_with_deepseek(prompt: str) -> str:
    load_dotenv_if_exists()

    api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("LLM_API_KEY")
    base_url = os.getenv("DEEPSEEK_BASE_URL") or os.getenv("LLM_BASE_URL") or "https://api.deepseek.com/v1"
    model = os.getenv("DEEPSEEK_MODEL") or os.getenv("LLM_MODEL") or "deepseek-chat"

    if not api_key:
        raise RuntimeError("Missing DEEPSEEK_API_KEY or LLM_API_KEY environment variable.")

    base_url = base_url.rstrip("/")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是严谨的科研助理，擅长用中文总结光学与计算成像论文。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 1400,
    }

    async with httpx.AsyncClient(timeout=60.0, headers=headers, follow_redirects=True, trust_env=True) as client:
        resp = await client.post(f"{base_url}/chat/completions", json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()


async def main() -> int:
    configure_utf8_stdio()

    parser = argparse.ArgumentParser()
    parser.add_argument("--author", default="Chao Zuo")
    parser.add_argument("--month", default=datetime.now().strftime("%Y-%m"), help="Month in YYYY-MM format")
    parser.add_argument("--year-from", type=int, default=datetime.now().year)
    parser.add_argument("--max-papers", type=int, default=10)
    parser.add_argument(
        "--abstract-chars",
        type=int,
        default=3000,
        help="Max abstract characters sent to DeepSeek per paper; use 0 for no truncation",
    )
    parser.add_argument(
        "--source",
        choices=("semantic", "all"),
        default="semantic",
        help="semantic is fast; all also scans Crossref journal pool and can be slow",
    )
    parser.add_argument(
        "--enrich-abstracts",
        action="store_true",
        help="Try Crossref and DOI/publisher pages to replace truncated abstracts before summarizing",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print collected paper data without calling DeepSeek")
    args = parser.parse_args()

    print("=" * 60)
    print(f"Chao Zuo monthly paper summary via DeepSeek: {args.month}")
    print("=" * 60)
    print("API key: read from environment only; value will not be printed.")

    if args.source == "semantic":
        print("Source mode: semantic (fast; skips Crossref journal scan)")
        papers = await search_by_author_semantic_scholar(
            args.author,
            max_results=50,
            year_from=args.year_from,
            allowed_journals=list(OPTICS_JOURNALS.keys()),
        )
    else:
        print("Source mode: all (Semantic Scholar + Crossref journal scan)")
        papers = await search_corresponding_papers(
            author_name=args.author,
            journals=None,
            max_per_journal=20,
            year_from=args.year_from,
        )

    month_papers = [p for p in papers if is_in_month(p, args.month)]
    month_papers = month_papers[: args.max_papers]

    print(f"\nCollected papers total: {len(papers)}")
    print(f"Papers in {args.month}: {len(month_papers)}")

    if not month_papers:
        print("\nNo papers matched this month. Try --month YYYY-MM or lower --year-from.")
        return 1

    for i, paper in enumerate(month_papers, 1):
        abstract_state = "has abstract" if paper.abstract else "no abstract"
        print(f"  [{i}] {paper.published} | {paper.journal} | {paper.title[:100]} ({abstract_state})")

    if args.enrich_abstracts:
        print("\nEnriching abstracts via Crossref and DOI/publisher pages...")
        await enrich_abstracts(month_papers)

    abstract_chars = args.abstract_chars if args.abstract_chars > 0 else None
    prompt = build_prompt(args.author, args.month, month_papers, abstract_chars)
    if args.dry_run:
        print("\nDry run enabled. Prompt preview:")
        print("-" * 60)
        print(prompt[:3000])
        if len(prompt) > 3000:
            print("\n... prompt truncated in preview ...")
        return 0

    print("\nCalling DeepSeek...")
    try:
        summary = await summarize_with_deepseek(prompt)
    except Exception as exc:
        print(f"DeepSeek summary failed: {type(exc).__name__}: {exc}")
        return 2

    print("\n" + "=" * 60)
    print("DeepSeek Summary")
    print("=" * 60)
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
