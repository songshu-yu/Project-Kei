"""Check Project Kei service health.

By default this does not call the LLM endpoint. Add --check-llm to send one
tiny OpenAI-compatible request through the API server.
"""
from __future__ import annotations

import argparse
import json

import httpx


def mark(ok: bool | None) -> str:
    if ok is True:
        return "OK"
    if ok is False:
        return "FAIL"
    return "SKIP"


def print_error(section: dict) -> None:
    if section.get("error"):
        print(f"  error: {section['error']}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000/health/full")
    parser.add_argument("--check-llm", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print raw JSON response")
    args = parser.parse_args()

    params = {"check_llm": "true" if args.check_llm else "false"}
    try:
        resp = httpx.get(args.url, params=params, timeout=60.0, trust_env=False)
    except httpx.HTTPError as exc:
        print(f"API: FAIL")
        print(f"  error: {type(exc).__name__}: {exc}")
        return 2

    print(f"status_code: {resp.status_code}")
    if resp.status_code != 200:
        print(resp.text)
        return 2

    data = resp.json()
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0 if data.get("status") == "ok" else 2

    api = data.get("api", {})
    asr = data.get("asr", {})
    tts = data.get("tts", {})
    llm = data.get("llm", {})

    print(f"API: {mark(api.get('ok'))}")
    print(f"ASR: {mark(asr.get('ok'))}  {asr.get('health_url', '')}")
    print_error(asr)
    print(f"TTS: {mark(tts.get('ok'))}  {tts.get('url', '')}")
    print_error(tts)

    configured = bool(llm.get("configured"))
    checked = bool(llm.get("checked"))
    llm_state = mark(llm.get("ok")) if checked else ("OK" if configured else "FAIL")
    suffix = "checked" if checked else "config only"
    print(f"LLM: {llm_state}  {suffix}  {llm.get('base_url', '')}  model={llm.get('model', '')}")
    print_error(llm)

    print(f"voice_ready: {data.get('voice_ready')}")
    print(f"overall: {data.get('status')}")
    return 0 if data.get("status") == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
