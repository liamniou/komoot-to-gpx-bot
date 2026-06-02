# komoot-to-gpx-bot

Telegram bot that converts Komoot tour links to GPX files. Supports both public smarttour/tour URLs (via Rust komootgpx) and private tours (via Python komootgpx with credentials).

## Env

- `BOT_TOKEN` (required) — Telegram bot token
- `ALLOWED_CHAT_ID` (required) — only this chat can talk to the bot
- `KOMOOT_EMAIL`, `KOMOOT_PASSWORD` (optional) — for private tours
