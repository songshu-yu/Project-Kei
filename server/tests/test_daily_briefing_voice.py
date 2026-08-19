"""Test daily briefing text and optional voice generation."""
from __future__ import annotations

import argparse
import httpx


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--fetch", action="store_true", help="Actually collect intel from configured sources")
    parser.add_argument("--rewrite", action="store_true", help="Ask LLM to rewrite as Kei")
    parser.add_argument("--voice", action="store_true", help="Generate GPT-SoVITS audio")
    parser.add_argument("--no-cache", action="store_true", help="Do not read today's cached briefing")
    parser.add_argument("--refresh", action="store_true", help="Force refresh and overwrite today's cache")
    parser.add_argument("--rewrite-refresh", action="store_true", help="Rewrite cached plain briefing with the current Kei prompt")
    parser.add_argument("--date", default="")
    args = parser.parse_args()

    endpoint = "/briefing/today/voice" if args.voice else "/briefing/today"
    method = "POST" if args.voice else "GET"
    params = {
        "fetch": "true" if args.fetch else "false",
        "rewrite": "true" if args.rewrite else "false",
        "cache": "false" if args.no_cache else "true",
        "refresh": "true" if args.refresh else "false",
        "rewrite_refresh": "true" if args.rewrite_refresh else "false",
    }
    if args.date:
        params["date"] = args.date

    url = args.api.rstrip("/") + endpoint
    with httpx.Client(timeout=600.0, trust_env=False) as client:
        resp = client.request(method, url, params=params)

    print(f"status: {resp.status_code}")
    if resp.status_code != 200:
        print(resp.text)
        return 2

    data = resp.json()
    print(f"date: {data.get('date')}")
    print(f"fetched: {data.get('fetched')} rewritten: {data.get('rewritten')}")
    print(f"cached: {data.get('cached')} cache_path: {data.get('cache_path', '')}")
    print(f"counts: {data.get('counts')}")
    print("\nPlain briefing:")
    print(data.get("text", ""))
    print("\nKei script:")
    print(data.get("script", ""))
    if data.get("audio_path"):
        print(f"\naudio_path: {data['audio_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
