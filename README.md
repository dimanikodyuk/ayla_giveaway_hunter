# Ayla Giveaway Hunter — Telegram widget dashboard hotfix (v3.2.2)

Only changed code: `app/widget.py`. Does not include `.env`, SQLite, Telegram session, or credentials.

## Changes
- Participation: server-side paging, 2 giveaways per page; navigation above and below cards (previous/next, current page / total).
- Dates: distinct chronological event timeline (winner announcement date first, otherwise deadline), with compact cards and original link; no duplicate participation action buttons.
- Both tabs show AI Score.
- Telegram widget HTML and compressed HTML remain within size limits.

## Install on Raspberry Pi
1. Back up `app/widget.py` and the database (recommended).
2. `sudo systemctl stop ayla-giveaway.service`
3. Extract ZIP **in** `/home/pi/ayla_giveaway_hunter/` preserving paths (do not replace database or .env).
4. `sudo systemctl start ayla-giveaway.service`
5. `sudo journalctl -u ayla-giveaway.service -n 50 --no-pager`
6. Send `/dashboard` to the Telegram bot to create a **new** widget. Old sent widgets may retain old HTML.

## Checks performed
- Python `py_compile` passed.
- JavaScript `node --check` passed.
- Dashboard HTML 7.6 KB, zlib compressed 2.85 KB (limits 32 KB / 4 KB).
- SQLite mock tests: 7 entries, 2 rows per page, 4 pages, distinct date labels; widget JSON response below 1024 bytes.

Not included: Telegram FloodWait protections (planned separate v3.3).
