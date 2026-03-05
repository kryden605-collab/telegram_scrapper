# main.py
import os
import json
import requests
from datetime import datetime, timedelta
from dateutil import parser
import pytz
from bs4 import BeautifulSoup
from apify import Actor

# ------------------------------
# Ініціалізація Apify Actor
# ------------------------------
actor_input = Actor.get_input()  # отримуємо input від користувача
CHANNELS = actor_input.get("channels", [])
DAYS_BACK = actor_input.get("daysBack", 1)
BATCH_SIZE = actor_input.get("batchSize", 80)

# для порівняння дат беремо UTC offset-naive
since_date = datetime.utcnow() - timedelta(days=DAYS_BACK)

# ------------------------------
# Функція для збору постів
# ------------------------------
def fetch_posts_from_channel(url):
    """
    Scrape пости та медіафайли з публічного Telegram-каналу через web view.
    Повертає список постів у форматі: {"id", "date", "text", "media"}
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
                if not date_span:
                    continue
                date_str = date_span.get("datetime")
                post_date = parser.isoparse(date_str)
                # UTC offset-naive
                post_date = post_date.astimezone(pytz.UTC).replace(tzinfo=None)

                if post_date < since_date:
                    continue

                # Парсимо медіафайли
                media = []
                for img in post_div.select("a.tgme_widget_message_photo_wrap img"):
                    media.append(img.get("src"))
                for video in post_div.select("div.tgme_widget_message_video_wrap a"):
                    media.append(video.get("href"))
                for doc in post_div.select("div.tgme_widget_message_document_wrap a"):
                    media.append(doc.get("href"))

                posts.append({
                    "id": post_id,
                    "date": post_date.isoformat(),
                    "text": text,
                    "media": media
                })

            except Exception as e:
                print(f"Error parsing a post: {e}")

    except Exception as e:
        print(f"Error fetching {url}: {e}")

    return posts

# ------------------------------
# Основний цикл по каналах
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

# Збереження батчів у окремі файли
for idx, batch in enumerate(batches, 1):
    batch_filename = f"batch_{idx}.json"
    with open(batch_filename, "w", encoding="utf-8") as f:
        json.dump(batch, f, ensure_ascii=False, indent=2)
    print(f"Saved batch {idx} with {len(batch)} posts to {batch_filename}")
