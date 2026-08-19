"""
test_intel.py — 情报系统逐模块测试
逐个检查每个数据源是否能正常采集

使用方式:
    cd server
    pip install httpx
    python test_intel.py            # 测试全部
    python test_intel.py arxiv      # 只测试 arXiv
    python test_intel.py github     # 只测试 GitHub
    python test_intel.py money      # 只测试信息差
    python test_intel.py full       # 测试完整情报汇总
"""

import sys
import _path_setup  # noqa: F401
import asyncio
import time
from datetime import datetime

# ============================================================
#  测试用配置（少量数据，快速验证）
# ============================================================

TEST_CONFIG = {
    "twitter_users": ["karpathy"],
    "github_users": ["karpathy"],
    "github_repos": ["RVC-Boss/GPT-SoVITS"],
    "bilibili_uids": [20259914],          # 填一个你关注的 UP 主 UID 来测试
    "youtube_channels": [],       # 填一个频道 ID 来测试
    "arxiv_keywords": ["phase retrieval"],
    "arxiv_authors": ["Laura Waller"],
    "money_rss": ["https://hnrss.org/frontpage"],
    "money_keywords": ["side project", "making money", "revenue", "startup"],
}


# ============================================================
#  颜色输出
# ============================================================

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

def ok(msg):     print(f"  {GREEN}✅ PASS{RESET}  {msg}")
def fail(msg):   print(f"  {RED}❌ FAIL{RESET}  {msg}")
def warn(msg):   print(f"  {YELLOW}⚠️  SKIP{RESET}  {msg}")
def info(msg):   print(f"  {CYAN}ℹ️  INFO{RESET}  {msg}")
def header(msg): print(f"\n{BOLD}{'='*50}\n  {msg}\n{'='*50}{RESET}")


# ============================================================
#  各模块测试
# ============================================================

async def test_arxiv():
    header("📄 测试 arXiv 论文追踪")
    from intel.collectors.arxiv import fetch_arxiv_papers

    print("\n  [1/2] 按关键词搜索...")
    t0 = time.time()
    papers = await fetch_arxiv_papers(
        categories=["eess.IV"],
        keywords=TEST_CONFIG["arxiv_keywords"],
        max_results=3, field_label="test",
    )
    elapsed = time.time() - t0

    if papers:
        ok(f"找到 {len(papers)} 篇论文 ({elapsed:.1f}s)")
        for p in papers[:2]:
            info(f"  {p.title[:70]}")
            info(f"  {', '.join(p.authors[:2])} | {p.published}")
    else:
        fail(f"未找到论文 ({elapsed:.1f}s)")

    print(f"\n  [2/2] 按作者搜索: {TEST_CONFIG['arxiv_authors'][0]}...")
    t0 = time.time()
    papers2 = await fetch_arxiv_papers(
        authors=TEST_CONFIG["arxiv_authors"],
        max_results=2, field_label="author_test",
    )
    elapsed = time.time() - t0

    if papers2:
        ok(f"找到 {len(papers2)} 篇 ({elapsed:.1f}s)")
        for p in papers2[:2]:
            info(f"  {p.title[:70]}")
    else:
        fail(f"未找到论文 ({elapsed:.1f}s)")

    return bool(papers or papers2)


async def test_github():
    header("🐙 测试 GitHub 动态")
    from intel.collectors.github import fetch_github_user_events, fetch_github_repo_releases

    user = TEST_CONFIG["github_users"][0]
    print(f"\n  [1/2] 用户活动: {user}...")
    t0 = time.time()
    events = await fetch_github_user_events([user])
    elapsed = time.time() - t0

    if events:
        ok(f"获取到 {len(events)} 条活动 ({elapsed:.1f}s)")
        for e in events[:3]:
            info(f"  {e.title}")
    else:
        warn(f"该用户最近没有公开活动 ({elapsed:.1f}s)")

    repo = TEST_CONFIG["github_repos"][0]
    print(f"\n  [2/2] 仓库 Release: {repo}...")
    t0 = time.time()
    releases = await fetch_github_repo_releases([repo])
    elapsed = time.time() - t0

    if releases:
        ok(f"找到 {len(releases)} 个 Release ({elapsed:.1f}s)")
        for r in releases[:2]:
            info(f"  {r.title}")
    else:
        warn(f"该仓库没有 Release ({elapsed:.1f}s)")

    return bool(events or releases)


async def test_twitter():
    header("🐦 测试 Twitter (Nitter)")
    from intel.collectors.twitter import fetch_twitter
    from intel.intel_config import NITTER_INSTANCES

    user = TEST_CONFIG["twitter_users"][0]
    print(f"\n  尝试获取 @{user} 的推文...")

    t0 = time.time()
    tweets = await fetch_twitter([user], NITTER_INSTANCES)
    elapsed = time.time() - t0

    if tweets:
        ok(f"获取到 {len(tweets)} 条推文 ({elapsed:.1f}s)")
        for t in tweets[:2]:
            info(f"  @{t.username}: {t.content[:60]}")
        return True
    else:
        fail(f"所有 Nitter 实例均失败 ({elapsed:.1f}s)")
        info("这是正常的 — 需要自建 Nitter 才能用")
        info("参考 docs/nitter-setup.md 部署")
        return False


async def test_bilibili():
    header("📺 测试 Bilibili")
    uids = TEST_CONFIG["bilibili_uids"]
    if not uids:
        warn("未配置 Bilibili UID，跳过")
        info("在脚本顶部 TEST_CONFIG 中添加 UID 来测试")
        return None

    from intel.collectors.bilibili import fetch_bilibili
    t0 = time.time()
    dynamics = await fetch_bilibili(uids, max_per_user=3)
    elapsed = time.time() - t0

    if dynamics:
        ok(f"获取到 {len(dynamics)} 条动态 ({elapsed:.1f}s)")
        for d in dynamics[:2]:
            info(f"  {d.username}: {d.content[:60]}")
        return True
    else:
        fail(f"获取失败 ({elapsed:.1f}s)")
        return False


async def test_youtube():
    header("▶️ 测试 YouTube")
    channels = TEST_CONFIG["youtube_channels"]
    if not channels:
        warn("未配置 YouTube 频道 ID，跳过")
        info("用 commentpicker.com/youtube-channel-id.php 查频道 ID")
        return None

    from intel.collectors.youtube import fetch_youtube
    t0 = time.time()
    videos = await fetch_youtube(channels, max_per_channel=3)
    elapsed = time.time() - t0

    if videos:
        ok(f"获取到 {len(videos)} 个视频 ({elapsed:.1f}s)")
        for v in videos[:2]:
            info(f"  [{v.channel}] {v.title[:50]}")
        return True
    else:
        fail(f"获取失败 ({elapsed:.1f}s)")
        return False


async def test_money_tips():
    header("💰 测试信息差情报")
    from intel.collectors.money_tips import fetch_money_tips

    print(f"\n  抓取 RSS 并用关键词过滤...")
    t0 = time.time()
    tips = await fetch_money_tips(
        rss_feeds=TEST_CONFIG["money_rss"],
        keywords=TEST_CONFIG["money_keywords"],
        max_results=5,
    )
    elapsed = time.time() - t0

    if tips:
        ok(f"找到 {len(tips)} 条相关信息 ({elapsed:.1f}s)")
        for t in tips[:3]:
            stars = "⭐" * min(t.score, 5)
            info(f"  {stars} [{t.source}] {t.title[:50]}")
        return True
    else:
        warn(f"RSS 已连接但未匹配到关键词 ({elapsed:.1f}s)")
        info("可以在 intel_config.py 中调整关键词范围")
        return True


async def test_full_briefing():
    header("📋 测试完整情报汇总")
    from intel.briefing import gather_all_intel, generate_briefing_text

    print("\n  并发采集所有数据源...")
    t0 = time.time()
    intel = await gather_all_intel()
    elapsed = time.time() - t0
    print(f"\n  采集完成，耗时 {elapsed:.1f}s")

    counts = {}
    for key, val in intel.items():
        if isinstance(val, list):
            counts[key] = len(val)

    if counts:
        info("各数据源结果:")
        for source, count in counts.items():
            status = f"{GREEN}✅{RESET}" if count > 0 else f"{YELLOW}⚠️{RESET}"
            print(f"    {status} {source}: {count} 条")

    briefing = generate_briefing_text(intel)
    total = sum(counts.values())

    if total > 0:
        ok(f"简报已生成: {len(briefing)} 字符, {total} 条数据")
        print(f"\n{CYAN}  --- 简报预览 ---{RESET}")
        for line in briefing.split("\n")[:15]:
            print(f"  {line}")
        print(f"  {CYAN}... (共 {len(briefing.split(chr(10)))} 行){RESET}")
    else:
        warn("所有数据源均为空，请检查 intel_config.py 配置")

    return total > 0


# ============================================================
#  主入口
# ============================================================

ALL_TESTS = {
    "arxiv":    ("📄 arXiv 论文",     test_arxiv),
    "github":   ("🐙 GitHub 动态",    test_github),
    "twitter":  ("🐦 Twitter/Nitter", test_twitter),
    "bilibili": ("📺 Bilibili",       test_bilibili),
    "youtube":  ("▶️  YouTube",        test_youtube),
    "money":    ("💰 信息差情报",      test_money_tips),
    "full":     ("📋 完整情报汇总",    test_full_briefing),
}


async def main():
    print(f"""
{BOLD}╔══════════════════════════════════════════╗
║    Project Kei — 情报系统测试工具        ║
║    {datetime.now().strftime('%Y-%m-%d %H:%M')}                         ║
╚══════════════════════════════════════════╝{RESET}
""")

    targets = sys.argv[1:] if len(sys.argv) > 1 else list(ALL_TESTS.keys())

    results = {}
    for key in targets:
        if key not in ALL_TESTS:
            print(f"{RED}未知测试: {key}{RESET}")
            print(f"可用: {', '.join(ALL_TESTS.keys())}")
            return

        name, test_fn = ALL_TESTS[key]
        try:
            result = await test_fn()
            results[name] = result
        except Exception as e:
            fail(f"{name} 抛出异常: {e}")
            results[name] = False

    # 汇总
    header("📊 测试结果汇总")
    passed = failed = skipped = 0

    for name, result in results.items():
        if result is True:
            print(f"  {GREEN}✅ PASS{RESET}    {name}")
            passed += 1
        elif result is False:
            print(f"  {RED}❌ FAIL{RESET}    {name}")
            failed += 1
        else:
            print(f"  {YELLOW}⏭️  SKIP{RESET}    {name}")
            skipped += 1

    print(f"\n  总计: {GREEN}{passed} 通过{RESET} / {RED}{failed} 失败{RESET} / {YELLOW}{skipped} 跳过{RESET}")

    if failed > 0:
        print(f"\n{YELLOW}  提示:")
        print(f"    Twitter 失败 → 需要自建 Nitter (见 docs/nitter-setup.md)")
        print(f"    Bilibili/YouTube 跳过 → 去 TEST_CONFIG 里填 UID/频道 ID{RESET}")


if __name__ == "__main__":
    asyncio.run(main())
