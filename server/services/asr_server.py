"""asr_server.py - Faster-Whisper ASR service for Project Kei.

Run on the PC:
    uvicorn services.asr_server:app --host 127.0.0.1 --port 8010

Environment:
    ASR_MODEL_SIZE=small
    ASR_DEVICE=cuda
    ASR_COMPUTE_TYPE=float16
    ASR_LANGUAGE=zh
"""
from __future__ import annotations

import os
import re
import tempfile
import threading
import traceback
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel


MODEL_SIZE = os.getenv("ASR_MODEL_SIZE", "small")
MODEL_PATH = os.getenv("ASR_MODEL_PATH", MODEL_SIZE)
DEVICE = os.getenv("ASR_DEVICE", "cuda")
COMPUTE_TYPE = os.getenv("ASR_COMPUTE_TYPE", "float16")
DEFAULT_LANGUAGE = os.getenv("ASR_LANGUAGE", "zh")
BEAM_SIZE = int(os.getenv("ASR_BEAM_SIZE", "5"))
MIN_SILENCE_MS = int(os.getenv("ASR_MIN_SILENCE_MS", "500"))
LOCAL_FILES_ONLY = os.getenv("ASR_LOCAL_FILES_ONLY", "false").lower() in {"1", "true", "yes"}
DEFAULT_INITIAL_PROMPT = os.getenv(
    "ASR_INITIAL_PROMPT",
    "这是和天童kei的中文语音对话。常见词：天童kei，kei，老师，叫你，叫我，称呼，回来，想你。"
    "如果用户在问称呼，优先识别为“叫你”，不要误写成“教你”。",
)
ENABLE_POSTPROCESS = os.getenv("ASR_ENABLE_POSTPROCESS", "true").lower() in {"1", "true", "yes"}

app = FastAPI(title="Project Kei ASR API", version="0.1.0")

_model = None
_model_lock = threading.Lock()


class SegmentOut(BaseModel):
    start: float
    end: float
    text: str


class TranscribeResponse(BaseModel):
    text: str
    language: str
    language_probability: float
    duration: float
    segments: List[SegmentOut]
    model_size: str
    device: str
    compute_type: str
    original_text: str = ""


def postprocess_text(text: str) -> str:
    fixed = text.strip()
    if not fixed:
        return fixed

    # Common name variants from Mandarin ASR. Keep the canonical romanized name.
    fixed = re.sub(r"(?i)\bkey\b", "kei", fixed)
    fixed = fixed.replace("凱怡", "kei").replace("凯怡", "kei")
    fixed = fixed.replace("凱伊", "kei").replace("凯伊", "kei")

    # In this companion dialogue, these short utterances are usually about names.
    fixed = fixed.replace("我教你什么合适", "我叫你什么合适")
    fixed = fixed.replace("我教你什麼合適", "我叫你什么合适")
    fixed = fixed.replace("我該教你什么", "我该叫你什么")
    fixed = fixed.replace("我该教你什么", "我该叫你什么")
    return fixed


def get_model():
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is not None:
            return _model
        from faster_whisper import WhisperModel

        print(
            f"[ASR] Loading faster-whisper model={MODEL_PATH} "
            f"device={DEVICE} compute_type={COMPUTE_TYPE}"
        )
        _model = WhisperModel(
            MODEL_PATH,
            device=DEVICE,
            compute_type=COMPUTE_TYPE,
            local_files_only=LOCAL_FILES_ONLY,
        )
        return _model


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "model_loaded": _model is not None,
        "model_size": MODEL_SIZE,
        "model_path": MODEL_PATH,
        "device": DEVICE,
        "compute_type": COMPUTE_TYPE,
        "language": DEFAULT_LANGUAGE,
        "local_files_only": LOCAL_FILES_ONLY,
    }


@app.post("/asr/transcribe", response_model=TranscribeResponse)
async def transcribe_audio(
    file: UploadFile = File(...),
    language: Optional[str] = Form(default=None),
    vad_filter: bool = Form(default=True),
    initial_prompt: Optional[str] = Form(default=None),
    postprocess: bool = Form(default=ENABLE_POSTPROCESS),
):
    suffix = Path(file.filename or "audio.wav").suffix or ".wav"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        audio_path = Path(tmp.name)
        tmp.write(await file.read())

    try:
        model = get_model()
        segments_iter, info = model.transcribe(
            str(audio_path),
            language=language or DEFAULT_LANGUAGE,
            beam_size=BEAM_SIZE,
            vad_filter=vad_filter,
            vad_parameters={"min_silence_duration_ms": MIN_SILENCE_MS},
            initial_prompt=initial_prompt if initial_prompt is not None else DEFAULT_INITIAL_PROMPT,
        )
        segments = [
            SegmentOut(start=float(seg.start), end=float(seg.end), text=seg.text.strip())
            for seg in segments_iter
        ]
        original_text = "".join(seg.text for seg in segments).strip()
        text = postprocess_text(original_text) if postprocess else original_text
        return TranscribeResponse(
            text=text,
            original_text=original_text,
            language=info.language,
            language_probability=float(info.language_probability),
            duration=float(info.duration),
            segments=segments,
            model_size=MODEL_SIZE,
            device=DEVICE,
            compute_type=COMPUTE_TYPE,
        )
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}") from exc
    finally:
        try:
            audio_path.unlink(missing_ok=True)
        except TypeError:
            if audio_path.exists():
                audio_path.unlink()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("services.asr_server:app", host="127.0.0.1", port=int(os.getenv("ASR_PORT", "8010")))
