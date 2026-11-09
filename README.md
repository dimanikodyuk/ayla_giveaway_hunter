# Ayla Giveaway Hunter v3.4 — patch

Base: latest supplied project ZIP plus v3.2.2 widget fix. Apply only on that lineage.

## Included
- `app/main.py`: authenticated read-only `/api/intelligence/calendar?days=30` and `/api/intelligence/insights`. Dates are shown in Europe/Kyiv; no guessed dates.
- `app/static/index.html`: Smart Calendar tab, explainable intelligence with missing-data warnings, responsive mobile web layout.
- `app/widget.py`: retains v3.2.2 pagination/date fix and sorts date tab by winner date first.

No .env, SQLite, sessions or service files. No database schema changes. Telegram widget-sandbox cannot directly access local web API; mobile web panel still requires LAN/VPN.

## Deployment
1. Back up current project and SQLite via SQLite backup API; stop `ayla-giveaway.service`.
2. Extract patch at project root, preserving paths.
3. `python3 -m compileall -q app` and restart service.
4. Check `/api/health`, open web panel and verify Calendar and Intelligence tab.
5. Send `/dashboard` to generate a fresh Telegram widget.

Rollback: restore the three changed files from your pre-install backup and restart.
