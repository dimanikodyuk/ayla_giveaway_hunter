# Ayla Giveaway Hunter v3.2 — Smart Discovery (patch)

## Changes
- `app/intelligence.py`: explainable 0–100 priority score and text-based scam warning signals. Not an AI model or probability of winning.
- `app/main.py`: additive SQLite schema migration v6, protected intelligence endpoints, analytics, manual channel candidate approval.
- `app/collector.py`: extracts public Telegram channel references from newly archived messages, including messages not classified as giveaways. Does not auto-join channels.
- `app/static/index.html`: Intelligence dashboard, risk signals, scores and manual channel review.

## Deployment (Raspberry Pi)
1. Back up SQLite using `sqlite3.Connection.backup()` or stop the service and copy the DB with its WAL files. Do not overwrite `.env`, `data/` or session files.
2. Stop `ayla-giveaway.service` (and any separately running collector service).
3. Unzip this patch into `/home/pi/ayla_giveaway_hunter` preserving relative paths.
4. Start services; inspect `journalctl -u ayla-giveaway.service -n 100 --no-pager`.
5. Open web panel, choose **Аналітика й AI Score**.
6. Channel discovery starts collecting evidence from NEW messages. Click **Знайти канали у старих повідомленнях** to scan the latest 5000 archived items without duplicate evidence.

## Limitations
- Heuristic rules only; no external LLM/API calls. Scores do not measure win odds.
- Discovery only from public t.me/telegram.me links in collected message text; channel links inside message IDs are ignored.
- New approved channels are created DISABLED until explicitly enabled. No automatic joins, no auto-participation.
- Scam detector signals are advisory; do not share Telegram login codes, seed phrases or pay unverified prize fees.
