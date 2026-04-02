---
name: telegram-tts
description: Convert text into speech audio and send it to a Telegram channel with the same text as caption. Use when the task needs broadcasting spoken updates, summaries, announcements, or any text-to-speech message into a Telegram channel or chat.
metadata:
  short-description: Send TTS audio to Telegram
---

# Telegram TTS

Use this skill when text should be turned into speech audio and sent to Telegram.

## Workflow

1. Use `run_skill_script`.
2. Set `skill_name` to `telegram-tts`.
3. Set `script_path` to `scripts/run.sh`.
4. Pass the text in env var `BUGO_TEXT`.
5. Pass the destination chat or channel id in env var `BUGO_CHANNEL_ID`.
6. Optionally pass `BUGO_TTS_VOICE` to force a specific Edge TTS voice.
6. Optionally set `timeout_seconds` if the request may take longer than the default.

## Required env

- `BUGO_TEXT`: text that will be synthesized and also used as the Telegram caption
- `BUGO_CHANNEL_ID`: target Telegram chat or channel id

## Optional env

- `BUGO_TTS_VOICE`: explicit Edge TTS voice name such as `en-US-AriaNeural` or `zh-CN-XiaoxiaoNeural`

## Notes

- The script prepares its own Python virtual environment and installs the required dependencies automatically.
- The script uses `BUGO_TTS_VOICE` when provided; otherwise it picks a default neural voice automatically based on the text content.
- The generated audio file is deleted before the script exits.
- Keep `BUGO_TEXT` concise enough for a normal Telegram caption.

