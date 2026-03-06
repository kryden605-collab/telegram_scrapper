import requests
import json
import re
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from apify import Actor


async def main():

    async with Actor:
        actor_input = await Actor.get_input() or {}

        channels = actor_input.get("channels", [])
        days_back = actor_input.get("daysBack", 1)

        cutoff_time = datetime.utcnow() - timedelta(days=days_back)

        all_posts = []

        for channel in channels:

            channel = channel.replace("https://t.me/", "").replace("@", "")
            url = f"https://t.me/s/{channel}"

            print(f"Scraping channel: {channel}")

            try:

                response = requests.get(url, timeout=20)
                soup = BeautifulSoup(response.text, "html.parser")

                messages = soup.select(".tgme_widget_message")

                for msg in messages:

                    try:

                        post_id = msg.get("data-post")

                        time_tag = msg.select_one("time")

                        if not time_tag:
                            continue

                        date_str = time_tag.get("datetime")

                        post_date = datetime.fromisoformat(
                            date_str.replace("Z", "+00:00")
                        ).replace(tzinfo=None)

                        if post_date < cutoff_time:
                            continue

                        text_block = msg.select_one(".tgme_widget_message_text")

                        text = ""
                        if text_block:
                            text = text_block.get_text(" ", strip=True)

                        post_link = f"https://t.me/{post_id}"

                        post_data = {
                            "channel": channel,
                            "id": post_id,
                            "date": post_date.isoformat(),
                            "text": text,
                            "url": post_link
                        }

                        await Actor.push_data(post_data)

                        all_posts.append(post_data)

                    except Exception as e:
                        print(f"Post parse error: {e}")

            except Exception as e:
                print(f"Channel error: {e}")

        print(f"Total posts collected: {len(all_posts)}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
