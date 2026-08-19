"""Diagnose the OpenAI-compatible LLM endpoint using server/.env.

The script never prints the API key value.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import _path_setup  # noqa: F401
import httpx

from core.env_loader import load_env_file, mask_env_names


SERVER_ROOT = Path(__file__).resolve().parents[1]


def _present(name: str) -> str:
    return "set" if os.getenv(name) else "unset"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--message", default="用一句中文回复：连接测试成功。")
    parser.add_argument("--timeout", type=float, default=45.0)
    args = parser.parse_args()

    loaded = load_env_file(SERVER_ROOT / ".env")
    api_key = os.getenv("LLM_API_KEY", "")
    base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")

    print("============================================================")
    print("LLM endpoint diagnostic")
    print("============================================================")
    print(f".env loaded keys: {mask_env_names(loaded)}")
    print(f"LLM_API_KEY: {'set' if api_key else 'unset'}")
    print(f"LLM_BASE_URL: {base_url}")
    print(f"LLM_MODEL: {model}")
    print("proxy environment:")
    for name in ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"]:
        print(f"  {name}: {_present(name)}")

    if not api_key:
        print("\nDiagnosis: LLM_API_KEY is missing. Put it in server/.env and restart the API.")
        return 2

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是一个简短回复的连接测试助手。"},
            {"role": "user", "content": args.message},
        ],
        "temperature": 0.2,
        "max_tokens": 64,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    url = f"{base_url}/chat/completions"
    print(f"\nPOST {url}")
    try:
        with httpx.Client(timeout=args.timeout, trust_env=True) as client:
            resp = client.post(url, json=payload, headers=headers)
        print(f"status: {resp.status_code}")
        if resp.status_code != 200:
            print(resp.text[:1000])
            return 3
        data = resp.json()
        text = data["choices"][0]["message"]["content"].strip()
        print("reply:")
        print(text)
        return 0
    except httpx.ProxyError as exc:
        print(f"proxy error: {type(exc).__name__}: {exc}")
        return 4
    except httpx.ConnectError as exc:
        print(f"connect error: {type(exc).__name__}: {exc}")
        return 5
    except httpx.ReadTimeout as exc:
        print(f"timeout: {type(exc).__name__}: {exc}")
        return 6
    except httpx.HTTPError as exc:
        print(f"httpx error: {type(exc).__name__}: {exc}")
        return 7


if __name__ == "__main__":
    raise SystemExit(main())
