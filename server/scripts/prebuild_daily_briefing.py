"""Prebuild today's Project Kei daily briefing cache through the running API."""
from __future__ import annotations

import argparse
from datetime import datetime

import httpx


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--date", default="")
    parser.add_argument("--voice", action="store_true", help="Also synthesize briefing audio")
    parser.add_argument("--no-rewrite", action="store_true", help="Skip Kei-style LLM rewrite")
    parser.add_argument("--refresh", action="store_true", help="Force refresh and overwrite today's cache")
    parser.add_argument("--no-refresh", action="store_true", help="Deprecated; cache is used by default")
    parser.add_argument("--rewrite-refresh", action="store_true", help="Rewrite cached briefing with the current Kei prompt")
    args = parser.parse_args()

    endpoint = "/briefing/today/voice" if args.voice else "/briefing/today"
    method = "POST" if args.voice else "GET"
    params = {
        "fetch": "true",
        "rewrite": "false" if args.no_rewrite else "true",
        "cache": "true",
        "refresh": "true" if args.refresh else "false",
        "rewrite_refresh": "true" if args.rewrite_refresh else "false",
    }
    if args.date:
        params["date"] = args.date

    url = args.api.rstrip("/") + endpoint
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Prebuilding daily briefing: {url}")
    print(f"refresh={args.refresh} rewrite_refresh={args.rewrite_refresh}")
    with httpx.Client(timeout=1200.0, trust_env=False) as client:
        resp = client.request(method, url, params=params)

    print(f"status: {resp.status_code}")
    if resp.status_code != 200:
        print(resp.text)
        return 2

    data = resp.json()
    print(f"date: {data.get('date')}")
    print(f"counts: {data.get('counts')}")
    print(f"cached: {data.get('cached')} cache_path: {data.get('cache_path', '')}")
    if data.get("audio_path"):
        print(f"audio_path: {data['audio_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
