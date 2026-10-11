# Daily digest by email or Telegram

After each `jobradar run`, you can get a short message with your top new matches, the CVs ready to send, upcoming interviews and status changes. It goes to you only. The tool never writes to companies.

Turn it on under `[notify]` in `config.toml`, put the secrets in `.env`, then check with `jobradar notify-test`.

## Telegram (easiest)

1. In Telegram, open **@BotFather**, send `/newbot`, pick a name. Copy the token into `.env` as `TELEGRAM_BOT_TOKEN`.
2. Open your new bot and send it any message, for example `/start`.
3. Run `jobradar telegram-id` and copy the printed line into `.env`.
4. Set `telegram = true` under `[notify]`.

## Email

Any mail account that allows SMTP works. Put these in `.env`:

```
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=you@example.com
SMTP_PASSWORD=...
DIGEST_TO=you@example.com
```

Gmail: use `smtp.gmail.com`, port 587, and an **App password** (Google Account, Security, 2 Step Verification, App passwords), not your normal password. Then set `email = true` under `[notify]`.

Port 465 uses SSL; any other port uses STARTTLS.
