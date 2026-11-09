# Ayla Giveaway Hunter — журнал змін

## v3.0 — Raspberry Pi Edition (2026-11-09)
- Інсталятор systemd для Raspberry Pi OS / Debian.
- Безпечне онлайн-резервування SQLite через SQLite Backup API; перевірка цілісності та захищене від випадкового перезапису відновлення.
- Єдина актуальна інструкція `README.md`.
- Автоматичний перезапуск сервісу після збою/втрати живлення (після завантаження ОС).
- Щоденний резервний запуск через systemd timer — опційно.
- Без зміни існуючої схеми SQLite, секретів та логіки Telegram Dashboard v2.4.

## v2.4
- Покращення контрастності Telegram Dashboard.

## v2.2–v2.3
- Метадані Telegram Giveaway та українські статуси віджета.

## v1.9–v2.1
- Тихі сповіщення та інтерактивний Telegram Dashboard.

## v3.1
- Host/port read from .env; updated example.
- Widget WON/LOST/ENTERED actions and persistent audit.
- Durable 24-hour auto-LOST and Telegram result reminder outbox.
- Lifecycle worker with restart/retry; browser session auth survives F5.

---
# Ayla Giveaway Hunter v3.1 — patch

Only modified/new files. Does not contain `.env`, SQLite databases or Telegram sessions.

## Deploy

1. **Stop service:** `sudo systemctl stop ayla-giveaway.service`
2. **Back up DB** before copying: `mkdir -p ~/ayla-backups && cp -a ~/ayla_giveaway_hunter/data/giveaways.sqlite3 ~/ayla-backups/giveaways-before-v31.sqlite3` (stop service first).
3. Unzip this patch into `/home/pi/ayla_giveaway_hunter`, preserving relative paths. Do not replace `.env` or `data/`.
4. Check `.env`: `HOST=0.0.0.0`, `PORT=8093`, `ENABLE_BOT=true`, `TG_BOT_ALLOWED_USER_IDS=...`. Keep secrets private.
5. `sudo systemctl start ayla-giveaway.service` then `sudo journalctl -u ayla-giveaway.service -n 70 --no-pager`.
6. Hard refresh browser (Ctrl+F5), sign in once. F5 should preserve auth within tab session.

## Behavior

- Only `ENTERED` and `AWAITING_RESULT` records with timezone-aware `winner_at` auto-close to `LOST` at `winner_at + 24 hours`. Existing `WON`/`LOST` statuses are never overwritten automatically.
- Telegram result reminder is queued between `winner_at` and `winner_at + 24 hours` (one per owner and winner timestamp); delivery uses the existing outbox and requires the Telegram bot to be enabled. If the device was offline the entire window, it closes the entry on recovery without a stale reminder.
- History is in `participation_audit`; old statuses are retained, and manual correction remains possible. API: `/api/giveaways/{id}/participation-history`.
- Lifecycle runs every 60s independent of Telegram bot; errors are logged and retried. SQLite WAL and FULL sync remain enabled.
- Telegram widgets depend on Telegram client support for `widget_query`.
- `sessionStorage` survives F5 but is accessible to same-origin JavaScript; only use this private UI on trusted devices.

## Note

`winner_at` is interpreted as an absolute timestamp with explicit UTC offset. A naive date is skipped for safety. A date edit changes future closure timing.
