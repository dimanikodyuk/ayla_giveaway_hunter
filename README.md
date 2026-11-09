# Ayla Giveaway Hunter v3.0

Самостійно розгорнутий пошук розіграшів: FastAPI вебпанель, Telegram Collector (Telethon), Telegram-бот з інтерактивним віджетом, SQLite.

## Важливо

- Зберігайте `.env`, `data/telegram_user.session` та SQLite лише приватно. Ніколи не надсилайте їх у публічний Git.
- **Вимкніть Windows-екземпляр перед запуском Raspberry Pi**: один і той самий Telegram-бот не повинен паралельно опитувати `getUpdates` з двох машин. Не використовуйте одну Telethon-сесію одночасно на двох хостах.
- За замовчуванням вебсервер слухає `127.0.0.1:8093`. Для доступу через LAN встановіть `HOST=0.0.0.0` лише у довіреній мережі, увімкніть авторизацію (`AUTH_MODE=token`, `GIVEAWAY_TOKEN`), і не відкривайте порт в інтернет. `AUTH_MODE=local` не дає доступу з інших пристроїв.
- Вбудований `widget-sandbox` може вимагати актуальний Telegram-клієнт. Звичайні Telegram-кнопки — резервний шлях.

## Перенесення Windows → Raspberry Pi 4

1. Зупиніть `launcher.py` на Windows. Створіть консистентну копію бази (SQLite WAL означає, що **не можна** копіювати лише відкритий `.sqlite3` без Backup API):

   ```powershell
   cd C:\GIT\ayla_giveaway_hunter
   .\.venv\Scripts\python.exe scripts\db_maintenance.py backup --file data\giveaways_transfer.sqlite3
   ```

   Якщо на Windows ще немає `scripts/db_maintenance.py`, розпакуйте патч v3.0 перед виконанням. Після зупинки програми можна також перенести всю папку `data` включно з WAL/SHM, але backup API надійніший.

2. На Raspberry Pi OS перевірте Python 3.11+ і створіть папку `~/ayla_giveaway_hunter`. Перенесіть код проєкту (версія v2.4 + патч v3.0), `.env`, **копію** бази та `data/telegram_user.session` (якщо Collector увімкнено). Не переносіть Windows `.venv`.

   ```powershell
   scp -r app deploy scripts tests requirements.txt README.md CHANGELOG.md pi@192.168.0.247:/home/pi/ayla_giveaway_hunter/
   scp .env pi@192.168.0.247:/home/pi/ayla_giveaway_hunter/.env
   scp data\giveaways_transfer.sqlite3 pi@192.168.0.247:/home/pi/ayla_giveaway_hunter/data/giveaways.sqlite3
   scp data\telegram_user.session pi@192.168.0.247:/home/pi/ayla_giveaway_hunter/data/telegram_user.session
   ```

   **Примітка:** `scp -r` з кількома файлами в одну директорію працює лише якщо ця директорія вже створена. Створіть її командою `ssh pi@192.168.0.247 "mkdir -p ~/ayla_giveaway_hunter/data"`. Замість IP використайте поточну адресу Raspberry Pi. Передавання секретів виконуйте лише через перевірене SSH-з'єднання.

3. На Raspberry Pi:

   ```bash
   sudo apt update
   sudo apt install -y python3-venv python3-pip
   cd ~/ayla_giveaway_hunter
   bash deploy/install_rpi4.sh
   sudo journalctl -u ayla-giveaway -n 80 --no-pager
   ```

4. Перевірте стан:

   ```bash
   systemctl is-active ayla-giveaway
   curl -fsS http://127.0.0.1:8093/api/health
   .venv/bin/python scripts/db_maintenance.py check
   ```

5. Після успішної перевірки Telegram `/dashboard` переконайтеся, що відображаються ваші участі та що Windows-екземпляр вимкнений.

## Резервні копії

```bash
cd ~/ayla_giveaway_hunter
.venv/bin/python scripts/db_maintenance.py backup
.venv/bin/python scripts/db_maintenance.py check
```

Для щоденних копій встановіть опційний timer (шаблони розраховані на `pi` та `/home/pi/ayla_giveaway_hunter`):

```bash
sudo cp deploy/ayla-giveaway-backup.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ayla-giveaway-backup.timer
systemctl list-timers ayla-giveaway-backup.timer
```

Копії зберігаються у `backups/` і **не видаляються автоматично**; контролюйте місце на SD-карті, періодично копіюйте архіви поза Raspberry Pi. За бажанням додайте окрему політику ротації. Копії `.env` і Telegram-сесії зберігайте окремо та захищено.

Відновлення: зупиніть сервіс `sudo systemctl stop ayla-giveaway`; збережіть поточні `giveaways.sqlite3`, `giveaways.sqlite3-wal`, `giveaways.sqlite3-shm` в окремій папці; переконайтеся, що цільова база та sidecar-файли відсутні; потім:

```bash
.venv/bin/python scripts/db_maintenance.py restore --file backups/ВАША_КОПІЯ.sqlite3 --yes-i-stopped-service
sudo systemctl start ayla-giveaway
```

## Діагностика

```bash
sudo systemctl status ayla-giveaway
sudo journalctl -u ayla-giveaway -f
ss -ltnp | grep 8093
```

Якщо Collector показує `TG_API_ID and TG_API_HASH are not configured`, перевірте ці змінні в `.env` без публікації їхніх значень. Якщо Telegram-бот отримує `Conflict: terminated by other getUpdates request`, вимкніть інший запущений екземпляр.

## Прибирання застарілих README

Після перевірки нового `README.md` видаліть старі `README_v*.md` вручну: `rm -f README_v*.md` (Linux) або `Remove-Item README_v*.md` (PowerShell). Патч навмисно не видаляє локальні файли.

## Правила оновлень

Оновлення постачаються **лише зміненими/новими файлами** зі збереженням шляхів. Один актуальний `README.md` та один `CHANGELOG.md`; `README_v*.md` більше не створюємо. `.env.example` постачається лише за зміни змінних. Патч не перезаписує `data/`, `.env` чи `.session`.
