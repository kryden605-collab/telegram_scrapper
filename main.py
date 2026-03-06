import requests
from bs4 import BeautifulSoup
from apify import Actor


def scrape_channel(channel, max_posts):
    url = f"https://t.me/s/{channel}"

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    response = requests.get(url, headers=headers, timeout=30)

    if response.status_code != 200:
        print(f"Failed to fetch {channel}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")

    messages = soup.select(".tgme_widget_message")

    posts = []

    for msg in messages[:max_posts]:

        text_el = msg.select_one(".tgme_widget_message_text")
        date_el = msg.select_one("time")

        text = text_el.get_text(" ", strip=True) if text_el else ""

        date = None
        if date_el and date_el.has_attr("datetime"):
            date = date_el["datetime"]

        link = None
        link_el = msg.select_one(".tgme_widget_message_date")
        if link_el and link_el.get("href"):
            link = link_el["href"]

        views = None
        views_el = msg.select_one(".tgme_widget_message_views")
        if views_el:
            views = views_el.text.strip()

        post = {
            "channel": channel,
            "date": date,
            "text": text,
            "views": views,
            "url": link
        }

        posts.append(post)

    return posts


async def main():

    async with Actor:

        input_data = await Actor.get_input() or {}

        channels = input_data.get("channels", [])
        max_posts = input_data.get("maxPosts", 80)

        total = 0

        for channel in channels:

            print(f"Scraping {channel}")

            try:
                posts = scrape_channel(channel, max_posts)

                for post in posts:
                    await Actor.push_data(post)

                print(f"{len(posts)} posts saved")

                total += len(posts)

            except Exception as e:
                print(f"Error scraping {channel}: {e}")

        print(f"Total posts collected: {total}")


if __name__ == "__main__":
    Actor.run(main)
