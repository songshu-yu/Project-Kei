"""Diagnose Weibo dynamic collection through RSSHub.

The project currently has no Weibo collector. This script probes RSSHub routes
so you can verify whether a Weibo UID can be read before wiring it into briefing.

Run from the server directory:
    python test_weibo_debug.py --uid 1195242865
"""
from __future__ import annotations

import _path_setup  # noqa: F401
import argparse
import asyncio
import os
import re
import sys
import xml.etree.ElementTree as ET

import httpx


PROXY_ENV_NAMES = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY")
DEFAULT_RSSHUBS = (
    "https://rsshub.app",
    "https://rsshub.rssforever.com",
)


def _clean_text(value):
    value = re.sub(r"<[^>]+>", "", value or "")
    return re.sub(r"\s+", " ", value).strip()


def _rss_items(root):
    items = root.findall(".//item")
    if items:
        return items
    return root.findall(".//{http://www.w3.org/2005/Atom}entry")


async def probe_rsshub(client, base, uid):
    base = base.rstrip("/")
    url = f"{base}/weibo/user/{uid}"
    print(f"\n[probe] GET {url}")
    try:
        resp = await client.get(url)
    except httpx.HTTPError as exc:
        print(f"  httpx error: {type(exc).__name__}: {exc}")
        return False
    except Exception as exc:
        print(f"  request error: {type(exc).__name__}: {exc}")
        return False

    print(f"  status: {resp.status_code}")
    print(f"  content-type: {resp.headers.get('content-type', '<missing>')}")
    print(f"  final-url: {resp.url}")
    if resp.status_code != 200:
        print(f"  body preview: {_clean_text(resp.text[:300])}")
        return False

    try:
        root = ET.fromstring(resp.text.lstrip())
    except ET.ParseError as exc:
        print(f"  XML parse error: {exc}")
        print(f"  body preview: {_clean_text(resp.text[:300])}")
        return False

    items = _rss_items(root)
    print(f"  items: {len(items)}")
    if items:
        title = items[0].findtext("title") or items[0].findtext("{http://www.w3.org/2005/Atom}title") or ""
        link = items[0].findtext("link") or ""
        print(f"  first title: {_clean_text(title)[:160]}")
        if link:
            print(f"  first link: {link}")
    return len(items) > 0


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--uid", required=True, help="Weibo numeric user UID")
    parser.add_argument("--rsshub", action="append", help="RSSHub base URL, can be repeated")
    parser.add_argument("--timeout", type=float, default=25.0)
    args = parser.parse_args()

    rsshub_bases = tuple(args.rsshub) if args.rsshub else DEFAULT_RSSHUBS

    print("=" * 60)
    print("Weibo RSSHub diagnostic")
    print("=" * 60)
    print(f"python: {sys.version.split()[0]}")
    print(f"httpx: {httpx.__version__}")
    print(f"uid: {args.uid}")
    print(f"rsshub bases: {list(rsshub_bases)}")
    print("\nproxy environment:")
    for name in PROXY_ENV_NAMES:
        print(f"  {name}={os.getenv(name) or '<unset>'}")

    headers = {
        "User-Agent": "ProjectKei/0.1 Weibo RSSHub diagnostic",
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
    }
    success_count = 0
    async with httpx.AsyncClient(
        timeout=args.timeout,
        headers=headers,
        follow_redirects=True,
        trust_env=True,
    ) as client:
        for base in rsshub_bases:
            if await probe_rsshub(client, base, args.uid):
                success_count += 1

    if success_count == 0:
        print("\nDiagnosis: no Weibo RSSHub route succeeded.")
        print("Most likely causes: bad UID, RSSHub public instance unavailable, route blocked, or proxy/network issue.")
        return 2
    print("\nDiagnosis: at least one Weibo RSSHub route succeeded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
