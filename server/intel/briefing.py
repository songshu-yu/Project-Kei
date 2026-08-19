"""Legacy briefing script and Python compatibility facade.

The main API assembles Collector 1.0 sources through
``features.daily_briefing.source_composition``.  This module preserves the
historical ``gather_all_intel``/CLI result shape for direct callers only.
"""
import asyncio, json, os
from datetime import datetime
from pathlib import Path
from intel.intel_config import *
from intel.collectors.twitter import fetch_twitter
from intel.collectors.github import fetch_github_user_events, fetch_github_repo_releases
from intel.collectors.bilibili import fetch_bilibili
from intel.collectors.youtube import fetch_youtube
from intel.collectors.arxiv import clear_arxiv_failures, fetch_arxiv_papers, get_arxiv_failures
from intel.collectors.papers import (
    fetch_recent_crossref_for_authors,
    search_by_author_semantic_scholar,
)
from intel.collectors.money_tips import fetch_money_tips
from services.intel_source_config import load_intel_sources

def _norm_author_name(value):
    return " ".join(str(value or "").replace(".", " ").lower().split())


def _unique_targets(values):
    """Keep first occurrence so priority groups win without duplicate requests."""
    result = []
    seen = set()
    for value in values:
        key = str(value or "").casefold().strip()
        if key and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _paper_author_names(paper):
    names = []
    matched = getattr(paper, "matched_author", "")
    if matched:
        names.append(matched)
    for author in getattr(paper, "authors", []) or []:
        if isinstance(author, str):
            names.append(author)
        elif isinstance(author, dict):
            name = " ".join(part for part in [author.get("given", ""), author.get("family", "")] if part)
            if name:
                names.append(name)
    return names

def _covered_authors(papers, authors):
    covered = set()
    author_map = {_norm_author_name(author): author for author in authors}
    for paper in papers:
        paper_names = [_norm_author_name(name) for name in _paper_author_names(paper)]
        for key, author in author_map.items():
            if any(key and (key == name or key in name or name in key) for name in paper_names):
                covered.add(author)
    return covered

async def gather_all_intel(sources=None, source_config_snapshot=None):
    print("="*50); print(f"  📡 开始采集情报 — {datetime.now().strftime('%Y-%m-%d %H:%M')}"); print("="*50)
    tasks = {}
    warnings = []
    selected_sources = set(sources or ["twitter", "github", "bilibili", "youtube", "money", "arxiv", "crossref", "semantic"])
    # PK-110 snapshots the non-secret source registry once per explicit
    # generation so every legacy source in that run sees one consistent view.
    # Direct legacy callers keep the historical lazy-load behavior.
    source_config = dict(source_config_snapshot) if source_config_snapshot is not None else load_intel_sources()
    twitter_users = source_config["twitter_users"]
    money_twitter_users = source_config["money_twitter_users"]
    github_users = source_config["github_users"]
    github_repos = source_config["github_repos"]
    bilibili_uids = source_config["bilibili_uids"]
    youtube_channel_ids = source_config["youtube_channel_ids"]
    tracked_authors_all = _unique_targets(
        source_config["paper_priority_authors"]
        + source_config["paper_secondary_authors"]
        + source_config["paper_ai_authors"]
    )
    clear_arxiv_failures()
    try:
        since_hours = int(os.getenv("PAPER_LOOKBACK_HOURS", os.getenv("ARXIV_SINCE_HOURS", str(ARXIV_SINCE_HOURS))))
    except ValueError:
        since_hours = ARXIV_SINCE_HOURS
    all_tw = _unique_targets(twitter_users + money_twitter_users)
    if "twitter" in selected_sources and all_tw: tasks["twitter"] = fetch_twitter(all_tw, NITTER_INSTANCES)
    if "github" in selected_sources and github_users: tasks["github_users"] = fetch_github_user_events(github_users)
    if "github" in selected_sources and github_repos: tasks["github_repos"] = fetch_github_repo_releases(github_repos)
    if "bilibili" in selected_sources and bilibili_uids: tasks["bilibili"] = fetch_bilibili(bilibili_uids, since_hours=since_hours)
    if "youtube" in selected_sources and youtube_channel_ids: tasks["youtube"] = fetch_youtube(youtube_channel_ids)
    if "money" in selected_sources and MONEY_CONFIG.get("rss_feeds"): tasks["money_tips"] = fetch_money_tips(MONEY_CONFIG["rss_feeds"], MONEY_CONFIG.get("keywords",[]))
    results = {}
    if tasks:
        gathered = await asyncio.gather(*tasks.values(), return_exceptions=True)
        for key, result in zip(tasks.keys(), gathered):
            if isinstance(result, Exception):
                warnings.append(f"{key} source failed ({type(result).__name__})")
                results[key] = []
            else:
                result_warnings = getattr(result, "warnings", None)
                if result_warnings:
                    warnings.extend(f"{key} source warning" for warning in result_warnings if warning)
                results[key] = result
    arxiv_results = []
    if "arxiv" in selected_sources:
        for fn, cfg in ARXIV_CONFIG.items():
            try:
                arxiv_results.extend(await fetch_arxiv_papers(
                    categories=cfg.get("categories",[]),
                    keywords=cfg.get("keywords",[]),
                    max_results=int(cfg.get("max_results", ARXIV_MAX_RESULTS)),
                    field_label=fn,
                    since_hours=since_hours,
                ))
            except Exception as e:
                error_type = type(e).__name__
                print(f"[arXiv] {fn} failed ({error_type})")
                warnings.append(f"arXiv {fn} source failed ({error_type})")
    enable_authors = os.getenv("ARXIV_ENABLE_AUTHORS", str(ARXIV_ENABLE_AUTHORS)).strip().lower() in {"1", "true", "yes", "on"}
    if "arxiv" in selected_sources and enable_authors and tracked_authors_all:
        try:
            author_limit = int(os.getenv("ARXIV_DAILY_AUTHOR_LIMIT", str(ARXIV_DAILY_AUTHOR_LIMIT)))
        except ValueError:
            author_limit = ARXIV_DAILY_AUTHOR_LIMIT
        try:
            author_max_results = int(os.getenv("ARXIV_AUTHOR_MAX_RESULTS", str(ARXIV_AUTHOR_MAX_RESULTS)))
        except ValueError:
            author_max_results = ARXIV_AUTHOR_MAX_RESULTS
        tracked_authors = tracked_authors_all[:max(author_limit, 0)]
        if tracked_authors:
            arxiv_results.extend(await fetch_arxiv_papers(
                authors=tracked_authors,
                max_results=author_max_results,
                field_label="tracked_authors",
                since_hours=since_hours,
            ))

    enable_crossref = os.getenv("PAPER_ENABLE_CROSSREF_DAILY_SCAN", str(PAPER_ENABLE_CROSSREF_DAILY_SCAN)).strip().lower() in {"1", "true", "yes", "on"}
    if "crossref" in selected_sources and enable_crossref and tracked_authors_all:
        try:
            try:
                crossref_max_per_journal = int(os.getenv("PAPER_CROSSREF_MAX_PER_JOURNAL", str(PAPER_CROSSREF_MAX_PER_JOURNAL)))
            except ValueError:
                crossref_max_per_journal = PAPER_CROSSREF_MAX_PER_JOURNAL
            crossref_papers = await fetch_recent_crossref_for_authors(
                tracked_authors_all,
                journals=None,
                since_hours=since_hours,
                max_per_journal=crossref_max_per_journal,
            )
            for paper in crossref_papers:
                paper.field = "crossref"
            arxiv_results.extend(crossref_papers)
        except Exception as e:
            error_type = type(e).__name__
            print(f"[Crossref] daily scan failed ({error_type})")
            warnings.append(f"Crossref paper scan failed ({error_type})")

    enable_semantic = os.getenv("PAPER_ENABLE_SEMANTIC_SCHOLAR", str(PAPER_ENABLE_SEMANTIC_SCHOLAR)).strip().lower() in {"1", "true", "yes", "on"}
    semantic_fallback_only = os.getenv("PAPER_SEMANTIC_SCHOLAR_FALLBACK_ONLY", str(PAPER_SEMANTIC_SCHOLAR_FALLBACK_ONLY)).strip().lower() in {"1", "true", "yes", "on"}
    if "semantic" in selected_sources and enable_semantic and tracked_authors_all:
        try:
            ss_limit = int(os.getenv("PAPER_SEMANTIC_SCHOLAR_AUTHOR_LIMIT", str(PAPER_SEMANTIC_SCHOLAR_AUTHOR_LIMIT)))
        except ValueError:
            ss_limit = PAPER_SEMANTIC_SCHOLAR_AUTHOR_LIMIT
        try:
            ss_max_results = int(os.getenv("PAPER_SEMANTIC_SCHOLAR_MAX_RESULTS", str(PAPER_SEMANTIC_SCHOLAR_MAX_RESULTS)))
        except ValueError:
            ss_max_results = PAPER_SEMANTIC_SCHOLAR_MAX_RESULTS

        if semantic_fallback_only:
            covered = _covered_authors(arxiv_results, tracked_authors_all)
            semantic_authors = [author for author in tracked_authors_all if author not in covered]
            print(f"[Semantic Scholar] fallback authors: {len(semantic_authors)} / {len(tracked_authors_all)}")
        else:
            semantic_authors = list(tracked_authors_all)

        semantic_failures = []
        for author in semantic_authors[:max(ss_limit, 0)]:
            try:
                semantic_papers = await search_by_author_semantic_scholar(
                    author,
                    max_results=ss_max_results,
                    year_from=None,
                    allowed_journals=None,
                    since_hours=since_hours,
                )
                for paper in semantic_papers:
                    paper.field = "semantic_scholar"
                arxiv_results.extend(semantic_papers)
            except Exception as e:
                print(f"[Semantic Scholar] daily author lookup failed ({type(e).__name__})")
                semantic_failures.append(author)
        if semantic_failures:
            warnings.append(f"Semantic Scholar fallback failed for {len(semantic_failures)} tracked authors")

    topic_names = set(ARXIV_CONFIG.keys())
    for failure in get_arxiv_failures():
        for name in topic_names:
            if f"arXiv {name}" in failure:
                warning = f"arXiv {name} source failed"
                if warning not in warnings:
                    warnings.append(warning)
                break

    seen_papers = set()
    deduped_papers = []
    for paper in arxiv_results:
        key = (getattr(paper, "doi", "") or getattr(paper, "url", "") or getattr(paper, "title", "")).lower()
        if key and key in seen_papers:
            continue
        if key:
            seen_papers.add(key)
        deduped_papers.append(paper)
    arxiv_results = deduped_papers
    results["papers"] = arxiv_results
    results["_warnings"] = warnings
    return results

def generate_briefing_text(intel):
    mx = BRIEFING_CONFIG.get("max_items_per_source", 5)
    lines = [f"📋 每日情报简报 — {datetime.now().strftime('%Y年%m月%d日 %H:%M')}", "="*50]
    tw = intel.get("twitter",[])
    if tw:
        lines.append(f"\n🐦 Twitter 动态 ({len(tw)}条)"); lines.append("-"*30)
        for t in tw[:mx]: lines.extend([f"  @{t.username}: {t.content[:100]}", f"  🔗 {t.url}", ""])
    gh = intel.get("github_users",[]) + intel.get("github_repos",[])
    if gh:
        lines.append(f"\n🐙 GitHub 动态 ({len(gh)}条)"); lines.append("-"*30)
        for e in gh[:mx]: lines.extend([f"  {e.title}", f"  🔗 {e.url}", ""])
    bili = intel.get("bilibili",[])
    if bili:
        lines.append(f"\n📺 Bilibili ({len(bili)}条)"); lines.append("-"*30)
        for d in bili[:mx]: lines.extend([f"  {d.username}: {d.content[:100]}", ""])
    yt = intel.get("youtube",[])
    if yt:
        lines.append(f"\n▶️ YouTube ({len(yt)}条)"); lines.append("-"*30)
        for v in yt[:mx]: lines.extend([f"  [{v.channel}] {v.title}", f"  🔗 {v.url}", ""])
    papers = intel.get("papers",[])
    if papers:
        lines.append(f"\n📄 最新论文 ({len(papers)}篇)"); lines.append("-"*30)
        by_f = {}
        for p in papers: by_f.setdefault(getattr(p, "field", getattr(p, "source", "paper")), []).append(p)
        for f, fps in by_f.items():
            fd = {"ai":"🤖 AI/深度学习","computational_imaging":"📸 计算成像","tracked_authors":"👤 关注作者"}.get(f,f)
            lines.append(f"\n  {fd}:")
            for p in fps[:mx]: lines.extend([f"    📌 {p.title}", f"       {', '.join(p.authors[:2])} | {p.published}", f"       {p.url}", ""])
    money = intel.get("money_tips",[])
    if money:
        lines.append(f"\n💰 信息差情报 ({len(money)}条)"); lines.append("-"*30)
        for n in money[:mx]: lines.extend([f"  {'⭐'*min(n.score,5)} [{n.source}] {n.title}", ""])
    if not any([tw,gh,bili,yt,papers,money]): lines.append("\n暂无新情报，请检查 intel_config.py 配置。")
    lines.extend(["="*50, "情报采集完毕。"])
    return "\n".join(lines)

def save_briefing(text):
    if not BRIEFING_CONFIG.get("save_history"): return
    d = Path(BRIEFING_CONFIG["history_dir"]); d.mkdir(exist_ok=True)
    fp = d / (datetime.now().strftime("%Y%m%d_%H%M") + ".txt")
    fp.write_text(text, encoding="utf-8"); print(f"[Briefing] 💾 已保存: {fp}")

async def run_briefing():
    intel = await gather_all_intel()
    briefing = generate_briefing_text(intel)
    save_briefing(briefing)
    print("\n" + briefing)
    return briefing

if __name__ == "__main__":
    asyncio.run(run_briefing())
