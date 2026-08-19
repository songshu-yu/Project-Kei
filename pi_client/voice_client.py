"""Raspberry Pi voice client for Project Kei.

Records audio on the Pi, uploads it to the PC API, downloads streamed reply
audio parts, and plays them immediately.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

import httpx


CLIENT_ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = CLIENT_ROOT / "output"
RECORDINGS_DIR = OUTPUT_DIR / "recordings"
REPLIES_DIR = OUTPUT_DIR / "replies"


def require_command(name: str) -> None:
    if shutil.which(name) is None:
        raise RuntimeError(f"Missing command: {name}. Install ALSA tools, for example: sudo apt install alsa-utils")


def record_press_enter(path: Path, sample_rate: int, device: str) -> Path:
    require_command("arecord")
    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "arecord",
        "-q",
        "-f",
        "S16_LE",
        "-r",
        str(sample_rate),
        "-c",
        "1",
        "-t",
        "wav",
    ]
    if device:
        cmd.extend(["-D", device])
    cmd.append(str(path))

    input("Press Enter to start recording...")
    print("Recording. Press Enter again to stop.")
    proc = subprocess.Popen(cmd)
    try:
        input()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

    if not path.exists() or path.stat().st_size <= 44:
        raise RuntimeError(f"No usable audio captured: {path}")
    print(f"Saved recording: {path}")
    return path


def record_fixed_seconds(path: Path, seconds: float, sample_rate: int, device: str) -> Path:
    require_command("arecord")
    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "arecord",
        "-q",
        "-f",
        "S16_LE",
        "-r",
        str(sample_rate),
        "-c",
        "1",
        "-t",
        "wav",
        "-d",
        str(max(1, int(seconds))),
    ]
    if device:
        cmd.extend(["-D", device])
    cmd.append(str(path))

    print(f"Recording {seconds:.1f}s... speak now.")
    subprocess.run(cmd, check=True)
    print(f"Saved recording: {path}")
    return path


def play_wav(path: Path, player: str) -> None:
    if not path.exists():
        print(f"Reply audio file not found: {path}")
        return
    if not player:
        player = "aplay"
    require_command(player)
    print(f"Playing: {path}")
    subprocess.run([player, "-q", str(path)], check=False)


def download_audio(api_base: str, audio_url: str, dest_dir: Path) -> Path:
    if not audio_url:
        raise RuntimeError("empty audio_url")
    url = urljoin(api_base.rstrip("/") + "/", audio_url.lstrip("/"))
    filename = Path(audio_url).name or f"reply_{int(time.time())}.wav"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename
    with httpx.Client(timeout=60.0) as client:
        resp = client.get(url)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
    return dest


def stream_voice_chat(
    api_base: str,
    audio_path: Path,
    language: str,
    vad_filter: bool,
    split_tts: bool,
    play: bool,
    player: str,
) -> dict:
    stream_url = urljoin(api_base.rstrip("/") + "/", "voice/chat/stream")
    final_result: dict = {}

    with audio_path.open("rb") as f:
        files = {"file": (audio_path.name, f, "audio/wav")}
        data = {
            "language": language,
            "vad_filter": "true" if vad_filter else "false",
            "split_tts": "true" if split_tts else "false",
        }
        with httpx.Client(timeout=300.0) as client:
            with client.stream("POST", stream_url, files=files, data=data) as resp:
                print(f"status: {resp.status_code}")
                if resp.status_code != 200:
                    print(resp.read().decode("utf-8", errors="replace"))
                    raise RuntimeError("voice chat stream request failed")

                for line in resp.iter_lines():
                    if not line:
                        continue
                    event = json.loads(line)
                    event_type = event.get("event")

                    if event_type == "reply":
                        final_result.update(event)
                        print(f"user_text: {event.get('user_text')}")
                        print(f"assistant_text: {event.get('assistant_text')}")
                        print(f"emotion: {event.get('emotion')}")
                        print(f"timings_ms_so_far: {event.get('timings_ms')}")
                    elif event_type == "audio_part":
                        print(
                            f"audio_part: {event.get('index')}/{event.get('total')} "
                            f"{event.get('elapsed_ms')}ms {event.get('audio_url')}"
                        )
                        audio_url = event.get("audio_url", "")
                        if audio_url:
                            wav_path = download_audio(api_base, audio_url, REPLIES_DIR)
                            if play:
                                play_wav(wav_path, player)
                    elif event_type == "done":
                        final_result.update(event)
                        print(f"audio_paths: {event.get('audio_paths')}")
                        print(f"timings_ms: {event.get('timings_ms')}")
                    elif event_type == "error":
                        raise RuntimeError(event.get("error", "stream error"))
                    else:
                        print(event)

    return final_result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", required=True, help="PC API base URL, e.g. http://192.168.1.23:8000")
    parser.add_argument("--language", default="zh")
    parser.add_argument("--seconds", type=float, default=0.0, help="Fixed recording length. Default: press Enter to stop.")
    parser.add_argument("--sample-rate", type=int, default=16000)
    parser.add_argument("--device", default="", help="Optional ALSA capture device, e.g. plughw:1,0")
    parser.add_argument("--player", default="aplay", help="Audio player command, default: aplay")
    parser.add_argument("--no-play", action="store_true")
    parser.add_argument("--no-split-tts", action="store_true")
    parser.add_argument("--vad", action="store_true", help="Enable ASR VAD")
    args = parser.parse_args()

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    audio_path = RECORDINGS_DIR / f"pi_mic_{timestamp}.wav"

    try:
        if args.seconds and args.seconds > 0:
            record_fixed_seconds(audio_path, args.seconds, args.sample_rate, args.device)
        else:
            record_press_enter(audio_path, args.sample_rate, args.device)

        stream_voice_chat(
            api_base=args.api,
            audio_path=audio_path,
            language=args.language,
            vad_filter=args.vad,
            split_tts=not args.no_split_tts,
            play=not args.no_play,
            player=args.player,
        )
        return 0
    except KeyboardInterrupt:
        print("\nCanceled.")
        return 130
    except Exception as exc:
        print(f"Error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
