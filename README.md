# Telegram Public Channel Scraper — Apify Actor

Щоденний моніторинг публічних Telegram-каналів через веб-скрапінг `t.me/s/`.  
**Без API-ключів, без Telethon, без реєстрації.**

---

## Як це працює

Актор звертається до публічного веб-інтерфейсу Telegram (`https://t.me/s/<channel>`),  
парсить HTML-сторінки та збирає текстові пости за останні N годин (за замовчуванням 24).

---

## Структура проєкту

```
telegram-scraper/
├── .actor/
│   ├── actor.json          # Метадані актора Apify
│   └── input_schema.json   # Схема вхідних даних (UI в Apify)
├── src/
│   └── main.py             # Основний код актора
├── Dockerfile              # Docker-образ для Apify
├── requirements.txt        # Python-залежності
└── README.md
```

---

## Вхідні параметри (Input)

| Параметр | Тип | За замовчуванням | Опис |
|---|---|---|---|
| `channels` | `string[]` | — | Список каналів (обов'язково) |
| `hoursBack` | `integer` | `24` | Глибина моніторингу в годинах |
| `maxPostsPerChannel` | `integer` | `200` | Максимум постів на канал |

### Формати каналів (всі підтримуються):
```json
[
  "durov",
  "@bbcnews",
  "https://t.me/reuters",
  "t.me/cnn"
]
```

---

## Вихідні дані (Output Dataset)

Кожен пост зберігається як окремий запис у датасеті Apify:

```json
{
  "channel": "bbcnews",
  "channel_url": "https://t.me/bbcnews",
  "post_id": "12345",
  "post_url": "https://t.me/bbcnews/12345",
  "text": "Повний текст поста...",
  "timestamp": "2024-01-15T10:30:00+00:00",
  "views": 15300,
  "scraped_at": "2024-01-15T11:00:00+00:00"
}
```

Додатково у Key-Value Store зберігається `SUMMARY` із загальною статистикою запуску.

---

## Деплой на Apify

### Варіант 1: через Apify CLI
```bash
npm install -g apify-cli
apify login
cd telegram-scraper
apify push
```

### Варіант 2: через GitHub інтеграцію
1. Завантажте папку в GitHub репозиторій
2. В Apify Console: **Actors → Create new → Link GitHub repo**

### Варіант 3: через ZIP
1. Заархівуйте папку `telegram-scraper/`
2. В Apify Console: **Actors → Create new → Upload ZIP**

---

## Налаштування щоденного запуску (Scheduler)

1. Відкрийте актор в Apify Console
2. Перейдіть у вкладку **Schedules**
3. Натисніть **Create schedule**
4. Cron: `0 6 * * *` (щодня о 06:00 UTC)
5. Вкажіть ваш `Input` зі списком каналів

---

## Обмеження

- Працює **тільки з публічними каналами** (у приватних `t.me/s/` недоступний)
- Telegram може тимчасово обмежувати часті запити (актор має вбудовані затримки та ретраї)
- Збираються тільки **текстові пости** (фото/відео без підпису ігноруються)

---

## Локальний запуск (для тестування)

```bash
pip install -r requirements.txt
# Створіть файл storage/key_value_stores/default/INPUT.json
# зі своїм input (див. приклад нижче)
python -m src.main
```

Приклад `INPUT.json`:
```json
{
  "channels": ["durov", "telegram", "bbcnews"],
  "hoursBack": 24,
  "maxPostsPerChannel": 50
}
```
