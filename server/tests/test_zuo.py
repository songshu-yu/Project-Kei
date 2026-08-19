"""test_zuo.py — 测试搜索左超(Chao Zuo)作为通讯作者的论文
左超 — 南京理工大学，结构光三维测量、相位恢复方向

使用方式:
    python test_zuo.py
"""
import asyncio
import _path_setup  # noqa: F401
from intel.collectors.papers import search_corresponding_papers, print_papers, OPTICS_JOURNALS


async def main():
    print("="*60)
    print("  Project Kei — 左超 Chao Zuo 通讯作者论文测试")
    print("="*60)

    # 1. 完整搜索（所有光学期刊）
    papers = await search_corresponding_papers(
        author_name="Chao Zuo",
        journals=None,           # None = 所有期刊
        max_per_journal=20,      # 每个期刊扫最近20篇
        year_from=2023,          # 只看2023年之后的
    )

    # 2. 全部论文
    print("\n" + "="*60)
    print("  📋 全部相关论文（含合作论文）")
    print("="*60)
    print_papers(papers, only_corresponding=False)

    # 3. 只看通讯作者论文
    print("\n" + "="*60)
    print("  🌟 仅通讯作者论文")
    print("="*60)
    print_papers(papers, only_corresponding=True)

    # 4. 按期刊分布统计
    print("\n" + "="*60)
    print("  📊 期刊分布统计")
    print("="*60)
    journal_count = {}
    for p in papers:
        j = p.journal or "未知"
        journal_count[j] = journal_count.get(j, 0) + 1

    for journal, count in sorted(journal_count.items(), key=lambda x: -x[1]):
        print(f"  {count:3d} 篇  —  {journal}")


if __name__ == "__main__":
    asyncio.run(main())
