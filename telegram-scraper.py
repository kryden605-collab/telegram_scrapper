import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import json

# Читаємо канал з аргументу командного рядка
import sys
if len(sys.argv) < 2:
    print("Usage: python telegram-scraper.py <channel_name>")
    sys.exit(1)

channel = sys.argv[1].strip()
print(f"Scraping channel: {channel}")

# Скільки днів назад збираємо
DAYS_BACK = 1
since_date = datetime.utcnow() - timedelta(days=DAYS_BACK)

# Базова адреса Telegram web
url = f"https://t.me/s/{channel}"

posts_data = []

# Для Telegram Web можна використовувати простий GET + парсинг HTML
try:
    r = requests.get(url)
    r.raise_for_status()
except Exception as e:
    print(f"Failed to fetch channel {channel}: {e}")
    sys.exit(1)

soup = BeautifulSoup(r.text, "html.parser")
posts = soup.find_all("div", class_="tgme_widget_message_wrap")

for post in posts:
    try:
        # дата посту
        date_tag = post.find("time")
        if not date_tag or not date_tag.has_attr("datetime"):
            continue
        post_date = datetime.fromisoformat(date_tag["datetime"].replace("Z", "+00:00"))

        # перевіряємо за 24h
        if post_date < since_date:
            continue

        # текст посту
        text_tag = post.find("div", class_="tgme_widget_message_text")
        text = text_tag.get_text(separator="\n") if text_tag else ""

        # лінки
        links = [a["href"] for a in post.find_all("a", href=True)]

        posts_data.append({
            "channel": channel,
            "date": post_date.isoformat(),
            "text": text,
            "links": links
        })
    except Exception as e:
        print(f"Error parsing a post: {e}")
        continue

# Зберігаємо у файл JSON
output_file = f"{channel}_posts.json"
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(posts_data, f, ensure_ascii=False, indent=2)

print(f"Saved {len(posts_data)} posts to {output_file}")
