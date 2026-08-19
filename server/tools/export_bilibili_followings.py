from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, List

import httpx

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = ROOT_DIR / ".env"
FOLLOWINGS_URL = "https://api.bilibili.com/x/relation/followings"


def load_env_file(path: Path) -> None:
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


def build_cookies() -> Dict[str, str]:
    mapping = {
        "SESSDATA": os.getenv("BILI_SESSDATA", "").strip(),
        "bili_jct": os.getenv("BILI_JCT", "").strip(),
        "buvid3": os.getenv("BILI_BUVID3", "").strip(),
    }
    return {key: value for key, value in mapping.items() if value}


def sanitize_comment(value: str) -> str:
    text = " ".join(str(value or "").split())
    return text.replace("#", "＃")[:80]


def matches_keywords(item: Dict, keywords: Iterable[str]) -> bool:
    words = [word.lower() for word in keywords if word]
    if not words:
        return True
    haystack = " ".join([
        str(item.get("uname", "")),
        str(item.get("sign", "")),
        str(item.get("official_verify", {}).get("desc", "")),
    ]).lower()
    return any(word in haystack for word in words)


def fetch_followings(uid: int, page_size: int, max_pages: int, delay: float, no_proxy: bool) -> List[Dict]:
    cookies = build_cookies()
    if not cookies.get("SESSDATA"):
        print("WARN: BILI_SESSDATA is not set; private or anti-bot protected followings may fail.", file=sys.stderr)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36",
        "Referer": f"https://space.bilibili.com/{uid}/fans/follow",
        "Origin": "https://space.bilibili.com",
        "Accept": "application/json, text/plain, */*",
    }

    results: List[Dict] = []
    page = 1
    trust_env = not no_proxy
    with httpx.Client(headers=headers, cookies=cookies, timeout=20.0, trust_env=trust_env) as client:
        while True:
            if max_pages and page > max_pages:
                break
            params = {"vmid": uid, "pn": page, "ps": page_size, "order": "desc"}
            response = client.get(FOLLOWINGS_URL, params=params)
            response.raise_for_status()
            payload = response.json()
            code = payload.get("code")
            if code != 0:
                raise RuntimeError(f"Bilibili API error code={code} message={payload.get('message')} data={payload.get('data')}")

            data = payload.get("data") or {}
            items = data.get("list") or []
            if not items:
                break

            results.extend(items)
            total = int(data.get("total") or 0)
            print(f"fetched page {page}: {len(items)} items, total={total}", file=sys.stderr)
            if total and len(results) >= total:
                break
            if len(items) < page_size:
                break
            page += 1
            if delay > 0:
                time.sleep(delay)
    return results


def output_python(items: List[Dict]) -> None:
    print("BILIBILI_UIDS = [")
    for item in items:
        mid = item.get("mid")
        uname = sanitize_comment(item.get("uname", ""))
        if mid:
            print(f"    {mid},  # {uname}")
    print("]")


def output_text(items: List[Dict]) -> None:
    for item in items:
        print(f"{item.get('mid')}\t{item.get('uname', '')}")


def output_json(items: List[Dict]) -> None:
    compact = [
        {
            "uid": item.get("mid"),
            "name": item.get("uname", ""),
            "sign": item.get("sign", ""),
            "official": (item.get("official_verify") or {}).get("desc", ""),
        }
        for item in items
    ]
    print(json.dumps(compact, ensure_ascii=False, indent=2))


def output_csv(items: List[Dict]) -> None:
    writer = csv.writer(sys.stdout)
    writer.writerow(["uid", "name", "sign", "official"])
    for item in items:
        writer.writerow([
            item.get("mid"),
            item.get("uname", ""),
            item.get("sign", ""),
            (item.get("official_verify") or {}).get("desc", ""),
        ])


def main() -> int:
    parser = argparse.ArgumentParser(description="Export Bilibili followings as UID lists for Project Kei.")
    parser.add_argument("--uid", type=int, required=True, help="Bilibili account UID whose followings should be exported.")
    parser.add_argument("--env", default=str(DEFAULT_ENV_FILE), help="Path to .env containing BILI_SESSDATA/BILI_JCT/BILI_BUVID3.")
    parser.add_argument("--ps", type=int, default=50, help="Page size, normally up to 50.")
    parser.add_argument("--max-pages", type=int, default=0, help="Stop after N pages; 0 means no explicit limit.")
    parser.add_argument("--delay", type=float, default=0.8, help="Delay between pages in seconds.")
    parser.add_argument("--keyword", action="append", default=[], help="Keep only UPs whose name/sign/official text contains this keyword. Can be repeated.")
    parser.add_argument("--format", choices=["python", "text", "json", "csv"], default="python", help="Output format.")
    parser.add_argument("--no-proxy", action="store_true", help="Ignore HTTP_PROXY/HTTPS_PROXY/ALL_PROXY for this request.")
    args = parser.parse_args()

    load_env_file(Path(args.env))
    items = fetch_followings(args.uid, max(1, min(args.ps, 50)), args.max_pages, args.delay, args.no_proxy)
    filtered = [item for item in items if matches_keywords(item, args.keyword)]

    seen = set()
    deduped = []
    for item in filtered:
        mid = item.get("mid")
        if mid and mid not in seen:
            seen.add(mid)
            deduped.append(item)

    print(f"exported {len(deduped)} / {len(items)} followings", file=sys.stderr)
    if args.format == "python":
        output_python(deduped)
    elif args.format == "text":
        output_text(deduped)
    elif args.format == "json":
        output_json(deduped)
    else:
        output_csv(deduped)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
