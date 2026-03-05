# main.py
import os
import json
import requests
from datetime import datetime, timedelta
from dateutil import parser
import pytz
from bs4 import BeautifulSoup

# ------------------------------
# Налаштування
# ------------------------------
DAYS_BACK = 1             # збирати пости за останні 24 години
BATCH_SIZE = 50           # розмір батчів
CHANNELS = [
    "https://t.me/s/channel1",
    "https://t.me/s/channel2",
    "https://t.me/s/channel3",
    # додайте до 30 каналів
]

utc = pytz.UTC
since_date = datetime.utcnow().replace(tzinfo=utc) - timedelta(days=DAYS_BACK)

# ------------------------------
# Функція для збору постів
# ------------------------------
def fetch_posts_from_channel(url):
    """
    Scrape пости з публічного Telegram-каналу через web view.
    Повертає список постів у форматі: {"id", "date", "text"}
    """
    posts = []
    try:
        r = requests.get(url)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        for post_div in soup.select("div.tgme_widget_message_wrap"):
            try:
                post_id = post_div.get("data-post")
                # Парсимо текст
                text_div = post_div.select_one("div.tgme_widget_message_text")
                text = text_div.get_text(strip=True) if text_div else ""
                # Парсимо дату
                date_span = post_div.select_one("time")
                if date_span:
                    date_str = date_span.get("datetime")
                    post_date = parser.isoparse(date_str)
                    if post_date.tzinfo is None:
                        post_date = post_date.replace(tzinfo=utc)
                    # Фільтр за останні 24h
                    if post_date >= since_date:
                        posts.append({
                            "id": post_id,
                            "date": post_date.isoformat(),
                            "text": text
                        })
            except Exception as e:
                print(f"Error parsing a post: {e}")

    except Exception as e:
        print(f"Error fetching {url}: {e}")
    
    return posts

# ------------------------------
# Основний цикл
# ------------------------------
all_posts = []
for channel_url in CHANNELS:
    print(f"Scraping channel: {channel_url}")
    posts = fetch_posts_from_channel(channel_url)

    # Збереження JSON
    channel_name = channel_url.rstrip("/").split("/")[-1]
    filename = f"{channel_name}_posts.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)

    print(f"Saved {len(posts)} posts to {filename}")
    all_posts.extend(posts)

print(f"Total posts collected: {len(all_posts)}")

# ------------------------------
# Батчування
# ------------------------------
batches = [all_posts[i:i + BATCH_SIZE] for i in range(0, len(all_posts), BATCH_SIZE)]
print(f"Total batches: {len(batches)}")
