# Ayla Giveaway Hunter v3.2.1 — AI Score navigation

Патч поверх **v3.2**. Тільки змінені файли, без `.env`, сесій та SQLite.

- У вкладці «Аналітика й AI Score» кожна оцінка має кнопку «Перейти до розіграшу», яка відкриває деталі запису.
- У каталозі та картці деталей показується AI Score без необхідності спершу відкривати вкладку аналітики.
- Окремий Telegram widget-sandbox показує бал і має кнопку переходу до оригіналу (бот надсилає посилання в особистий чат через наявний обробник `url:`).
- Telegram dashboard widget-sandbox показує AI Score поруч із назвою кожного розіграшу; кнопка «Оригінал» уже існувала.
- Оцінка — евристичний пріоритет, а не ймовірність виграшу.

## Установка

```bash
sudo systemctl stop ayla-giveaway.service
cd ~/ayla_giveaway_hunter
unzip -o /шлях/до/Ayla_Giveaway_Hunter_v3.2.1_PATCH.zip
sudo systemctl start ayla-giveaway.service
sudo journalctl -u ayla-giveaway.service -n 50 --no-pager
```

Перезавантаж вебсторінку Ctrl+F5. Для Telegram створи новий widget командою `/widget ID` або `/dashboard`, щоб застосувати оновлений HTML.
