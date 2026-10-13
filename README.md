# Ethio Lottery Telegram Bot (starter demo)

A Telegram bot starter with daily tickets (100 ETB), weekly (50 ETB), monthly (50 ETB), six-digit numbers, random/manual selection, unique numbers per draw, ticket history, results, countdowns, and admin commands.

**Demo only:** no money is collected and no prizes are paid. Real ETB payment integration is not included.

## Setup
1. In Telegram, open **@BotFather**, send `/newbot`, follow the prompts, and copy the token privately.
2. Find your numeric Telegram user ID using a trusted method.
3. Deploy these files to a Python hosting service. Set environment variables:
   - `BOT_TOKEN` = token from BotFather
   - `ADMIN_IDS` = your numeric Telegram ID (comma-separated for multiple admins)
   - `DB_PATH` = `lottery.db` locally; for hosted deployment use a persistent disk path.
4. Install dependencies with `pip install -r requirements.txt`, then run `python bot.py`.
5. Open your bot in Telegram and send `/start`.

## Commands
Players: `/start`, `/buy`, `/tickets`, `/results`, `/countdowns`.
Admins: `/admin`, `/result daily 123456`, `/result weekly 123456`, `/result monthly 123456`, `/close daily`, `/open daily`, `/stats`.

Cutoff countdowns are set to 20:00 Ethiopia time. The bot does not automatically close a draw at cutoff; admins must close it. Results are applied to the currently active draw key.

## Deployment
`render.yaml` is included as a starting blueprint for Render. Add the environment variables during deployment. Free-tier limits and persistent disk availability may change; confirm your host's current terms. A persistent disk or managed database is necessary to keep tickets after restarts.

## Before any real-money launch
This is not production-ready for real money. Confirm Ethiopian lottery/gambling licensing, legal requirements, tax and age restrictions, consumer-protection rules, and payment-provider approval. Real payment processing must use provider-side verification and secure reconciliation; screenshots or user claims are not proof of payment. Add backups, monitoring, audit logs, rate limits, stronger admin security, and independent draw-integrity review before public use.
