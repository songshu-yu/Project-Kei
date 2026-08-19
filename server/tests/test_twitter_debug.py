"""Diagnose why the Twitter/Nitter collector is failing.

Run from the server directory:
    python test_twitter_debug.py

Optional:
    python test_twitter_debug.py --user karpathy
    python test_twitter_debug.py --instance https://nitter.privacydev.net
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

from intel.intel_config import NITTER_INSTANCES, TWITTER_USERS
from intel.collectors.twitter import fetch_twitter


PROXY_ENV_NAMES = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY")


def _redact(value: str | None) -> str:
    if not value:
        return "<unset>"
    if "@" in value:
        scheme, _, rest = value.partition("://")
        host = rest.rsplit("@", 1)[-1]
        return f"{scheme}://<redacted>@{host}" if scheme else f"<redacted>@{host}"
    return value


def _clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", "", value or "")
    return re.sub(r"\s+", " ", value).strip()


async def probe_instance(client: httpx.AsyncClient, instance: str, user: str) -> bool:
    url = f"{instance.rstrip('/')}/{user}/rss"
    print(f"\n[probe] GET {url}")

    try:
        resp = await client.get(url)
    except httpx.ProxyError as exc:
        print(f"  proxy error: {type(exc).__name__}: {exc}")
        return False
    except httpx.ConnectError as exc:
        print(f"  connect error: {type(exc).__name__}: {exc}")
        return False
    except httpx.TimeoutException as exc:
        print(f"  timeout: {type(exc).__name__}: {exc}")
        return False
    except httpx.HTTPError as exc:
        print(f"  httpx error: {type(exc).__name__}: {exc}")
        return False

    print(f"  status: {resp.status_code}")
    print(f"  content-type: {resp.headers.get('content-type', '<missing>')}")
    print(f"  final-url: {resp.url}")

    if resp.status_code != 200:
        print(f"  body preview: {_clean_text(resp.text[:300])}")
        return False

    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError as exc:
        print(f"  XML parse error: {exc}")
        print(f"  body preview: {_clean_text(resp.text[:300])}")
        return False

    items = root.findall(".//item")
    print(f"  rss items: {len(items)}")
    if items:
        title = _clean_text(items[0].findtext("title", ""))
        print(f"  first title: {title[:160]}")
    return True


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--user", default=None, help="Twitter username to test")
    parser.add_argument("--instance", default=None, help="Single Nitter instance URL to test")
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()

    users = [args.user] if args.user else list(TWITTER_USERS[:2])
    instances = [args.instance] if args.instance else list(NITTER_INSTANCES)

    print("=" * 60)
    print("Twitter/Nitter collector diagnostic")
    print("=" * 60)
    print(f"python: {sys.version.split()[0]}")
    print(f"httpx: {httpx.__version__}")
    print(f"users: {users}")
    print(f"instances: {instances}")
    print("\nproxy environment:")
    for name in PROXY_ENV_NAMES:
        print(f"  {name}={_redact(os.getenv(name))}")

    headers = {
        "User-Agent": "ProjectKei/0.1 Nitter diagnostic",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    }

    success_count = 0
    async with httpx.AsyncClient(
        timeout=args.timeout,
        headers=headers,
        follow_redirects=True,
        trust_env=True,
    ) as client:
        for user in users:
            for instance in instances:
                if await probe_instance(client, instance, user):
                    success_count += 1

    print("\n" + "=" * 60)
    print("Calling the real fetch_twitter() once")
    print("=" * 60)
    try:
        tweets = await fetch_twitter(users, instances)
        print(f"fetch_twitter returned {len(tweets)} tweets")
        for tweet in tweets[:3]:
            print(f"  @{tweet.username}: {tweet.content[:120]}")
    except Exception as exc:
        print(f"fetch_twitter raised {type(exc).__name__}: {exc}")
        return 1

    if success_count == 0:
        print("\nDiagnosis: no Nitter RSS request succeeded.")
        print("Most likely causes: proxy not set for this PowerShell window, Nitter instances down, or the remote node cannot reach them.")
        return 2

    print("\nDiagnosis: at least one Nitter RSS request succeeded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
