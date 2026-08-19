"""Diagnose YouTube RSS collection.

Run from the server directory:
    python test_youtube_debug.py --channel UCbfYPyITQ-7l4upoX8nvctg

If no --channel is provided, it uses YOUTUBE_CHANNELS from intel_config.py.
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

from intel.intel_config import YOUTUBE_CHANNELS
from intel.collectors.youtube import NS, fetch_youtube


PROXY_ENV_NAMES = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY")
DEFAULT_TEST_CHANNEL = "UCbfYPyITQ-7l4upoX8nvctg"  # Two Minute Papers


def _clean_text(value):
    value = re.sub(r"<[^>]+>", "", value or "")
    return re.sub(r"\s+", " ", value).strip()


async def probe_channel(client, channel_id):
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    print(f"\n[probe] GET {url}")
    try:
        resp = await client.get(url)
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
        root = ET.fromstring(resp.text.lstrip())
    except ET.ParseError as exc:
        print(f"  XML parse error: {exc}")
        print(f"  body preview: {_clean_text(resp.text[:300])}")
        return False

    channel_title = root.findtext("atom:title", channel_id, NS)
    entries = root.findall("atom:entry", NS)
    print(f"  channel: {channel_title}")
    print(f"  entries: {len(entries)}")
    if entries:
        print(f"  first title: {_clean_text(entries[0].findtext('atom:title', '', NS))[:160]}")
    return True


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--channel", action="append", help="YouTube channel ID, can be repeated")
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()

    channels = args.channel or list(YOUTUBE_CHANNELS) or [DEFAULT_TEST_CHANNEL]

    print("=" * 60)
    print("YouTube RSS collector diagnostic")
    print("=" * 60)
    print(f"python: {sys.version.split()[0]}")
    print(f"httpx: {httpx.__version__}")
    print(f"channels: {channels}")
    print("\nproxy environment:")
    for name in PROXY_ENV_NAMES:
        print(f"  {name}={os.getenv(name) or '<unset>'}")

    headers = {
        "User-Agent": "ProjectKei/0.1 YouTube RSS diagnostic",
        "Accept": "application/atom+xml, application/xml, text/xml, */*",
    }
    success_count = 0
    async with httpx.AsyncClient(
        timeout=args.timeout,
        headers=headers,
        follow_redirects=True,
        trust_env=True,
    ) as client:
        for channel_id in channels:
            if await probe_channel(client, channel_id):
                success_count += 1

    print("\n" + "=" * 60)
    print("Calling the real fetch_youtube() once")
    print("=" * 60)
    videos = await fetch_youtube(channels, max_per_channel=3)
    print(f"fetch_youtube returned {len(videos)} videos")
    for video in videos[:5]:
        print(f"  [{video.channel}] {video.published} {video.title[:120]}")

    if success_count == 0:
        print("\nDiagnosis: no YouTube RSS request succeeded.")
        return 2
    print("\nDiagnosis: at least one YouTube RSS request succeeded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
