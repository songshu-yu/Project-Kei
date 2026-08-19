"""Test and use Project Kei affection/random event system.

Examples:
    python test_affection_system.py
    python test_affection_system.py --event daily
    python test_affection_system.py --choose warm
    python test_affection_system.py --status
"""
from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

os.environ["PROJECT_KEI_ENV_FILE"] = str(Path(tempfile.gettempdir()) / "project-kei-pk160-tests" / "missing.env")

import _path_setup  # noqa: E402,F401

from systems.affection_system import AffectionStore, choose_response, get_status, reset, trigger_event


def print_status(status) -> None:
    level = status["level"]
    print(
        f"affection={status['affection']} level={level['name']} "
        f"trust={status['trust']} mood={status['mood']} energy={status['energy']}"
    )
    if level["next_name"]:
        print(f"next={level['next_name']} in {level['points_to_next']} points")


def print_event(result) -> None:
    event = result.event
    print(f"[event] {event['title']}")
    print(f"scene: {event['scene']}")
    print(f"kei: {event['text']}")
    print(f"voice cue: {event.get('voice_cue')} - {event.get('voice_cue_description')}")
    print("choices:")
    for choice in event["choices"]:
        print(f"  {choice['id']}: {choice['text']}")


def demo() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = AffectionStore(Path(tmp) / "affection_state.json")
        print("[demo] initial")
        print_status(get_status(store=store))

        result = trigger_event(context="daily", seed=7, store=store)
        print()
        print_event(result)

        choice_id = result.event["choices"][0]["id"]
        result = choose_response(choice_id, store=store)
        print(f"\n[demo] choose {choice_id}")
        print(f"kei: {result.reply}")
        print(f"effects: {result.effects}")
        print_status(result.stats)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--event", nargs="?", const="", help="Trigger a random event with optional context")
    parser.add_argument("--force-event", default="", help="Trigger a specific event id")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--choose", help="Resolve the active event with a choice id")
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    if args.reset:
        count = reset()
        print(f"Reset complete: cleared {count} history records.")
        return 0

    if args.status:
        print_status(get_status())
        return 0

    if args.choose:
        result = choose_response(args.choose)
        print(f"kei: {result.reply or result.message}")
        print(f"effects: {result.effects}")
        print_status(result.stats)
        return 0

    if args.event is not None or args.force_event:
        result = trigger_event(context=args.event or "", force_event=args.force_event, seed=args.seed)
        print_event(result)
        return 0

    demo()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
