import subprocess
import os
import json
import time
from datetime import datetime, timedelta
from apify import Actor


async def main():

    async with Actor:

        actor_input = await Actor.get_input() or {}

        channels = actor_input.get("channels", [])
        hours = actor_input.get("hours_back", 24)

        since_time = datetime.utcnow() - timedelta(hours=hours)

        for channel in channels:

            print(f"Scraping: {channel}")

            result = subprocess.run(
                ["python", "main.py", channel],
                capture_output=True,
                text=True
            )

            try:
                posts = json.loads(result.stdout)
            except:
                print("Parsing error")
                continue

            for post in posts:

                try:
                    post_date = datetime.fromisoformat(post["date"])
                except:
                    continue

                if post_date >= since_time:

                    await Actor.push_data({
                        "channel": channel,
                        "date": post["date"],
                        "text": post.get("text"),
                        "views": post.get("views"),
                        "forwards": post.get("forwards"),
                        "replies": post.get("replies"),
                        "link": post.get("link")
                    })

            time.sleep(5)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
