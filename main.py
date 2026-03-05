import os
import subprocess
import time
import gc

for post in posts: 
    posts = posts[:100]

channels = os.getenv("CHANNELS", "")
channels = channels.split(",")

for channel in channels:

    print(f"Scraping {channel}")

    subprocess.run([
        "python",
        "telegram-scraper.py",
        channel.strip()
    ])

    # очищаємо памʼять
    gc.collect()

    # пауза щоб Telegram не блокував
    time.sleep(5)

print("DONE")
