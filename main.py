# main.py
import os
import json
from datetime import datetime, timedelta, timezone
from dateutil import parser
import requests
from bs4 import BeautifulSoup
from apify import Actor

# ------------------------------
# Ініціалізація Apify Actor
# ------------------------------
actor_input = Actor.get_input()
CHANNELS = actor_input.get("channels", [])
DAYS_BACK = actor_input.get("daysBack", 1)
BATCH_SIZE = actor_input.get("batchSize", 80)

# Завжди використовуємо UTC-aware дату
since_date = datetime.now(timezone.utc) - timedelta(days=DAYS_BACK)

# ------------------------------
# Функція для збору постів
# ------------------------------
def fetch_posts_from_channel(url):
    posts = []
    try:
        r = requests.get(url)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        for post_div in soup.select("div.tgme_widget_message_wrap"):
            try:
                post_id = post_div.get("data-post")
                # Текст
                text_div = post_div.select_one("div.tgme_widget_message_text")
                text = text_div.get_text(strip=True) if text_div else ""

                # Дата
                date_span = post_div.select_one("time")
                if date_span:
                    post_date = parser.isoparse(date_span.get("datetime"))

                    # Перетворюємо на UTC-aware завжди
                    if post_date.tzinfo is None:
                        post_date = post_date.replace(tzinfo=timezone.utc)
                    else:
                        post_date = post_date.astimezone(timezone.utc)

                    # Фільтруємо по даті
                    if post_date < since_date:
                        continue

                    # Медіа
                    media_urls = []
                    for img in post_div.select("a.tgme_widget_message_photo_wrap"):
                        href = img.get("href") or img.get("data-full")
                        if href:
                            media_urls.append(href)

                    posts.append({
                        "id": post_id,
                        "date": post_date.isoformat(),
                        "text": text,
                        "media": media_urls
                    })
            except Exception as e:
                print(f"Error parsing a post: {e}")

    except Exception as e:
        print(f"Error fetching {url}: {e}")

    return posts

# ------------------------------
# Основний цикл з батчуванням на диск
# ------------------------------
for channel_url in CHANNELS:
    print(f"Scraping channel: {channel_url}")
    posts = fetch_posts_from_channel(channel_url)

    channel_name = channel_url.rstrip("/").split("/")[-1]

    # Батчування і запис одразу на диск
    for i in range(0, len(posts), BATCH_SIZE):
        batch = posts[i:i + BATCH_SIZE]
        filename = f"{channel_name}_posts_batch_{i//BATCH_SIZE + 1}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(batch, f, ensure_ascii=False, indent=2)
        print(f"Saved batch {i//BATCH_SIZE + 1} ({len(batch)} posts) to {filename}")

    print(f"Total posts scraped from {channel_name}: {len(posts)}")
