---
name: telegram-reaction
description: Add or update a Telegram message reaction through the Bot API. Use when a task needs to react to an existing Telegram message with an emoji such as ⚡, 👍, ❤️, 👀, or to clear reactions on a specific message by chat_id and message_id.
---

# Telegram Reaction

Use this skill when a Telegram message needs a reaction.

## Workflow

1. Use `run_skill_script`.
2. Set `skill_name` to `telegram-reaction`.
3. Set `script_path` to `scripts/run.sh`.
4. Pass the destination chat id in `BUGO_CHAT_ID`.
5. Pass the target message id in `BUGO_MESSAGE_ID`.
6. Pass the emoji in `BUGO_REACTION_EMOJI`.
7. Optionally set `BUGO_REACTION_BIG=1` to request a big animation.
8. Optionally set `BUGO_REACTION_EMOJI` to an empty string to clear reactions.

## Required env

- `BUGO_CHAT_ID`: Telegram chat id containing the target message
- `BUGO_MESSAGE_ID`: target Telegram message id

## Optional env

- `BUGO_REACTION_EMOJI`: emoji to apply; leave empty to clear reactions
- `BUGO_REACTION_BIG`: `1`, `true`, or `yes` to request a big reaction animation
- `BUGO_TELEGRAM_TOKEN`: Telegram bot token; if omitted, the script will try `TELEGRAM_BOT_TOKEN`

## Notes

- The script prepares its own Python virtual environment and installs required dependencies automatically.
- The script calls Bot API `setMessageReaction`.
- Success output is compact JSON with `status`, `chat_id`, `message_id`, and `emoji`.
