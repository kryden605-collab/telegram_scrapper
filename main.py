import asyncio
import json
import re
from datetime import datetime, timezone, timedelta

import httpx
from bs4 import BeautifulSoup
from apify import Actor


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
REQUEST_DELAY       = 2.0
CHANNEL_DELAY       = 4.0
MAX_RETRIES         = 3
WEBHOOK_TIMEOUT     = 60.0
WEBHOOK_RETRY_DELAY = 10.0


def normalize_channel(raw: str) -> str:
    raw = raw.strip()
    match = re.search(r"(?:t\.me|telegram\.me)/([A-Za-z0-9_]+)", raw)
    if match:
        return match.group(1)
    return raw.lstrip("@")


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def parse_views(el) -> int | None:
    if not el:
        return None
    text = el.get_text(strip=True).upper().replace(",", "")
    try:
        if "K" in text:
            return int(float(text.replace("K", "")) * 1_000)
        if "M" in text:
            return int(float(text.replace("M", "")) * 1_000_000)
        return int(text)
    except ValueError:
        return None


def extract_text(msg) -> str:
    el = msg.select_one(".tgme_widget_message_text")
    if not el:
        return ""
    for br in el.find_all("br"):
        br.replace_with("\n")
    text = el.get_text(separator="", strip=False)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def extract_post_id(msg) -> str | None:
    link = msg.select_one(".tgme_widget_message_date")
    if link and link.get("href"):
        m = re.search(r"/(\d+)$", link["href"])
        return m.group(1) if m else None
    return None


async def fetch_html(client: httpx.AsyncClient, url: str) -> str | None:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = await client.get(url, headers=HEADERS, timeout=30.0, follow_redirects=True)
            if r.status_code == 200:
                return r.text
            if r.status_code == 429:
                Actor.log.warning(f"Rate limited — waiting 30s (attempt {attempt})")
                await asyncio.sleep(30)
            else:
                Actor.log.warning(f"HTTP {r.status_code} for {url} (attempt {attempt})")
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            Actor.log.warning(f"Network error {url} attempt {attempt}: {exc}")
            if attempt < MAX_RETRIES:
                await asyncio.sleep(5 * attempt)
    return None


async def scrape_channel(
    client: httpx.AsyncClient,
    channel: str,
    cutoff: datetime,
    max_posts: int,
) -> list[dict]:
    base_url = f"https://t.me/s/{channel}"
    page_url = base_url
    results: list[dict] = []
    seen_ids: set[str] = set()
    stop = False

    Actor.log.info(f"-> @{channel}")

    while not stop and len(results) < max_posts:
        html = await fetch_html(client, page_url)
        if not html:
            Actor.log.error(f"  Could not fetch {page_url}")
            break

        soup = BeautifulSoup(html, "html.parser")
        messages = soup.select(".tgme_widget_message")
        if not messages:
            break

        for msg in messages:
            post_id = extract_post_id(msg)
            if not post_id or post_id in seen_ids:
                continue
            seen_ids.add(post_id)

            time_tag = msg.select_one("time")
            post_dt = parse_datetime(time_tag.get("datetime") if time_tag else None)

            if post_dt and post_dt < cutoff:
                stop = True
                continue

            text = extract_text(msg)
            if not text:
                continue

            link_el = msg.select_one(".tgme_widget_message_date")
            results.append({
                "channel":     channel,
                "channel_url": f"https://t.me/{channel}",
                "post_id":     post_id,
                "url":         link_el.get("href") if link_el else None,
                "date":        post_dt.isoformat() if post_dt else None,
                "text":        text,
                "views":       parse_views(msg.select_one(".tgme_widget_message_views")),
                "scraped_at":  datetime.now(timezone.utc).isoformat(),
            })

        if stop:
            break

        oldest_id = extract_post_id(messages[-1])
        if not oldest_id:
            break
        page_url = f"{base_url}?before={oldest_id}"
        await asyncio.sleep(REQUEST_DELAY)

    Actor.log.info(f"  @{channel}: {len(results)} posts")
    return results


async def send_to_make(
    client: httpx.AsyncClient,
    webhook_url: str,
    payload: dict,
) -> bool:
    headers = {"Content-Type": "application/json"}
    body = json.dumps(payload, ensure_ascii=False)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = await client.post(
                webhook_url,
                content=body,
                headers=headers,
                timeout=WEBHOOK_TIMEOUT,
            )
            if r.status_code in (200, 201, 202, 204):
                Actor.log.info(f"Make.com webhook OK (HTTP {r.status_code})")
                return True
            else:
                Actor.log.warning(f"Make.com HTTP {r.status_code} (attempt {attempt}): {r.text[:200]}")
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            Actor.log.warning(f"Webhook error attempt {attempt}: {exc}")

        if attempt < MAX_RETRIES:
            await asyncio.sleep(WEBHOOK_RETRY_DELAY * attempt)

    Actor.log.error("Failed to deliver webhook to Make.com")
    return False


async def main():
    async with Actor:
        inp = await Actor.get_input() or {}

        raw_channels: list[str] = inp.get("channels", [])
        hours_back: int         = int(inp.get("hoursBack", 24))
        max_posts: int          = int(inp.get("maxPosts", 80))
        webhook_url: str        = inp.get("makeWebhookUrl", "").strip()

        channels = [normalize_channel(c) for c in raw_channels if c.strip()]

        if not channels:
            Actor.log.error("No channels provided in input.")
            return

        if not webhook_url:
            Actor.log.warning("makeWebhookUrl not set — data saved to dataset only.")

        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        Actor.log.info(f"Channels: {len(channels)} | window: {hours_back}h | cutoff: {cutoff.isoformat()}")

        all_posts: list[dict] = []

        async with httpx.AsyncClient() as client:
            for channel in channels:
                try:
                    posts = await scrape_channel(client, channel, cutoff, max_posts)
                    if posts:
                        await Actor.push_data(posts)
                    all_posts.extend(posts)
                except Exception as exc:
                    Actor.log.error(f"Error scraping @{channel}: {exc}")
                await asyncio.sleep(CHANNEL_DELAY)

        Actor.log.info(f"Scraping done. Total posts: {len(all_posts)}")

        if webhook_url and all_posts:
            payload = {
                "run_at":             datetime.now(timezone.utc).isoformat(),
                "hours_back":         hours_back,
                "total_posts":        len(all_posts),
                "channels_monitored": channels,
                "breakdown": {
                    ch: sum(1 for p in all_posts if p["channel"] == ch)
                    for ch in channels
                },
                "posts": all_posts,
            }
            async with httpx.AsyncClient() as client:
                await send_to_make(client, webhook_url, payload)
        elif not all_posts:
            Actor.log.warning("No posts collected — webhook not sent.")

        Actor.log.info("Done.")


if __name__ == "__main__":
    asyncio.run(main())
