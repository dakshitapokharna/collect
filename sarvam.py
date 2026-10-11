import base64
import json
import os
import re

import requests
from dotenv import load_dotenv

load_dotenv()

BASE = "https://api.sarvam.ai"
CHAT_MODEL = os.getenv("SARVAM_CHAT_MODEL", "sarvam-105b-conversations")
STT_WS_URL = (
    "wss://api.sarvam.ai/speech-to-text/ws?model=saaras:v3&mode=codemix&language-code=hi-IN"
    "&sample_rate=16000&input_audio_codec=pcm_s16le&vad_signals=true"
)


def ws_headers():
    return {"Api-Subscription-Key": _headers()["api-subscription-key"]}


def _headers():
    key = os.getenv("SARVAM_API_KEY")
    if not key:
        raise RuntimeError("SARVAM_API_KEY missing in .env")
    return {"api-subscription-key": key}


def transcribe(audio_bytes: bytes) -> str:
    r = requests.post(
        f"{BASE}/speech-to-text",
        headers=_headers(),
        files={"file": ("audio.wav", audio_bytes, "audio/wav")},
        data={"model": "saarika:v2.5", "language_code": "unknown"},
        timeout=60,
    )
    r.raise_for_status()
    return r.json().get("transcript", "").strip()


def chat(messages: list[dict], temperature: float = 0.5) -> str:
    r = requests.post(
        f"{BASE}/v1/chat/completions",
        headers={**_headers(), "Content-Type": "application/json"},
        json={"model": CHAT_MODEL, "messages": messages, "temperature": temperature},
        timeout=60,
    )
    r.raise_for_status()
    text = r.json()["choices"][0]["message"]["content"]
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()


def chat_stream(messages: list[dict], temperature: float = 0.5):
    """Yield text deltas as the model produces them."""
    with requests.post(
        f"{BASE}/v1/chat/completions",
        headers={**_headers(), "Content-Type": "application/json"},
        json={"model": CHAT_MODEL, "messages": messages, "temperature": temperature, "stream": True},
        stream=True,
        timeout=60,
    ) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line.startswith(b"data: {"):
                continue
            choices = json.loads(line[6:]).get("choices") or []
            if choices:
                delta = (choices[0].get("delta") or {}).get("content")
                if delta:
                    yield delta


def speak(text: str) -> bytes:
    r = requests.post(
        f"{BASE}/text-to-speech",
        headers={**_headers(), "Content-Type": "application/json"},
        json={
            "text": text[:1500],
            "target_language_code": "hi-IN",
            "speaker": "priya",
            "model": "bulbul:v3",
        },
        timeout=60,
    )
    r.raise_for_status()
    return base64.b64decode(r.json()["audios"][0])
