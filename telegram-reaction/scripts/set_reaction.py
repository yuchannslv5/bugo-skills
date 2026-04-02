import json
import os
import sys

import requests


def fail(message: str, code: str, *, stderr: str = "") -> None:
    payload = {"error": message, "error_code": code}
    if stderr:
        payload["stderr"] = stderr
    print(json.dumps(payload, ensure_ascii=False))
    sys.exit(1)


def truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def main() -> None:
    chat_id = os.environ.get("BUGO_CHAT_ID", "").strip()
    message_id = os.environ.get("BUGO_MESSAGE_ID", "").strip()
    emoji = os.environ.get("BUGO_REACTION_EMOJI", "").strip()
    is_big = truthy(os.environ.get("BUGO_REACTION_BIG", ""))
    token = os.environ.get("BUGO_TELEGRAM_TOKEN", "").strip() or os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()

    if not chat_id:
        fail("BUGO_CHAT_ID is required", "MISSING_CHAT_ID")
    if not message_id:
        fail("BUGO_MESSAGE_ID is required", "MISSING_MESSAGE_ID")
    if not token:
        fail("BUGO_TELEGRAM_TOKEN is required", "MISSING_TELEGRAM_TOKEN")

    reaction = []
    if emoji:
        reaction = [{"type": "emoji", "emoji": emoji}]

    url = f"https://api.telegram.org/bot{token}/setMessageReaction"
    response = requests.post(
        url,
        json={
            "chat_id": chat_id,
            "message_id": int(message_id),
            "reaction": reaction,
            "is_big": is_big,
        },
        timeout=60,
    )

    try:
        body = response.json()
    except ValueError:
        body = {"ok": False, "description": response.text}

    if response.status_code >= 400 or not body.get("ok"):
        fail(
            "Telegram setMessageReaction request failed",
            "TELEGRAM_API_ERROR",
            stderr=json.dumps(body, ensure_ascii=False),
        )

    print(
        json.dumps(
            {
                "status": "ok",
                "chat_id": chat_id,
                "message_id": int(message_id),
                "emoji": emoji,
                "is_big": is_big,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
