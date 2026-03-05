import os
import subprocess
import json
from datetime import datetime, timedelta

# Список каналів (можна винести у input.json або input_schema)
CHANNELS = [
    "channel1",
    "channel2",
    "channel3",
    # ... до 30 каналів
]

# Скільки днів назад збираємо
DAYS_BACK = 1
BATCH_SIZE = 80  # або 80
since_date = datetime.utcnow() - timedelta(days=DAYS_BACK)

all_posts = []

for channel in CHANNELS:
    print(f"Scraping channel: {channel}")

    # Викликаємо telegram-scraper.py через subprocess
    try:
        subprocess.run(
            ["python", "telegram-scraper.py", channel],
            check=True
        )
        # Читаємо результати
        output_file = f"{channel}_posts.json"
        if os.path.exists(output_file):
            with open(output_file, "r", encoding="utf-8") as f:
                posts = json.load(f)
            # Фільтруємо ще раз на випадок
            posts = [p for p in posts if datetime.fromisoformat(p["date"]) >= since_date]
            all_posts.extend(posts)
    except subprocess.CalledProcessError as e:
        print(f"Error scraping channel {channel}: {e}")
        continue

print(f"Total posts collected: {len(all_posts)}")

# Батчування
batches = [all_posts[i:i + BATCH_SIZE] for i in range(0, len(all_posts), BATCH_SIZE)]

# Зберігаємо кожен батч у окремий файл
for idx, batch in enumerate(batches, start=1):
    batch_file = f"batch_{idx}.json"
    with open(batch_file, "w", encoding="utf-8") as f:
        json.dump(batch, f, ensure_ascii=False, indent=2)
    print(f"Saved batch {idx} with {len(batch)} posts to {batch_file}")

# Готово, тепер ці батчі можна подавати на GPT Етап 1 (екстракція)
