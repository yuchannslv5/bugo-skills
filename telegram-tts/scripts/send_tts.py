import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Optional

import edge_tts
import requests


def fail(message: str, code: str, *, stderr: str = "") -> None:
    payload = {
        "error": message,
        "error_code": code,
    }
    if stderr:
        payload["stderr"] = stderr
    print(json.dumps(payload, ensure_ascii=False))
    sys.exit(1)


def choose_voice(text: str) -> str:
    ascii_chars = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    cjk_chars = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    if cjk_chars > ascii_chars:
        return "zh-CN-XiaoxiaoNeural"
    return "en-US-AriaNeural"


async def synthesize_to_file(text: str, voice: str, output_path: Path) -> None:
    communicator = edge_tts.Communicate(text=text, voice=voice)
    await communicator.save(str(output_path))


def main() -> None:
    text = os.environ.get("BUGO_TEXT", "").strip()
    channel_id = os.environ.get("BUGO_CHANNEL_ID", "").strip()
    token = os.environ.get("BUGO_TELEGRAM_TOKEN", "").strip()
    configured_voice = os.environ.get("BUGO_TTS_VOICE", "").strip()

    if not text:
        fail("BUGO_TEXT is required", "MISSING_TEXT")
    if not channel_id:
        fail("BUGO_CHANNEL_ID is required", "MISSING_CHANNEL_ID")
    if not token:
        fail("BUGO_TELEGRAM_TOKEN is required", "MISSING_TELEGRAM_TOKEN")

    temp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_file:
            temp_path = Path(temp_file.name)

        voice = configured_voice or choose_voice(text)
        asyncio.run(synthesize_to_file(text, voice, temp_path))

        url = f"https://api.telegram.org/bot{token}/sendVoice"
        with temp_path.open("rb") as audio_file:
            response = requests.post(
                url,
                data={
                    "chat_id": channel_id,
                    "caption": text,
                },
                files={
                    "voice": ("speech.mp3", audio_file, "audio/mpeg"),
                },
                timeout=60,
            )

        try:
            body = response.json()
        except ValueError:
            body = {"ok": False, "description": response.text}

        if response.status_code >= 400 or not body.get("ok"):
            fail(
                "Telegram sendVoice request failed",
                "TELEGRAM_API_ERROR",
                stderr=json.dumps(body, ensure_ascii=False),
            )

        result = body.get("result") or {}
        message_id = result.get("message_id")
        chat = result.get("chat") or {}
        print(
            json.dumps(
                {
                    "status": "sent",
                    # "chat_id": chat.get("id", channel_id),
                    # "message_id": message_id,
                    # "caption": text,
                    # "voice": voice,
                },
                ensure_ascii=False,
            )
        )
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass


if __name__ == "__main__":
    main()

