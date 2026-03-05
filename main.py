from apify import Actor
from playwright.async_api import async_playwright

async def main():
    async with Actor:
        actor_input = await Actor.get_input()

        channels = actor_input.get("channels", [])

        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()

            for channel in channels:

                url = f"https://t.me/s/{channel}"
                await page.goto(url)

                posts = await page.query_selector_all(".tgme_widget_message")

                for post in posts:

                    text_el = await post.query_selector(".tgme_widget_message_text")
                    date_el = await post.query_selector("time")

                    if text_el:

                        text = await text_el.inner_text()
                        date = await date_el.get_attribute("datetime")

                        await Actor.push_data({
                            "channel": channel,
                            "text": text,
                            "date": date
                        })

            await browser.close()

Actor.run(main)
