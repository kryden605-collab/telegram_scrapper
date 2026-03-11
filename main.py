import asyncio
import json
import random
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

REQUEST_DELAY       = 1.0
CONCURRENT_CHANNELS = 5
MAX_RETRIES         = 3
WEBHOOK_TIMEOUT     = 60.0
WEBHOOK_RETRY_DELAY = 10.0
HISTORY_DAYS        = 7

_semaphore: asyncio.Semaphore | None = None


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
    global _semaphore
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with _semaphore:
                await asyncio.sleep(REQUEST_DELAY + random.uniform(0.3, 1.2))
                r = await client.get(url, headers=HEADERS, timeout=30.0, follow_redirects=True)

            if r.status_code == 200:
                return r.text
            if r.status_code == 429:
                wait = 30 + random.uniform(5, 15)
                Actor.log.warning(f"Rate limited — waiting {wait:.0f}s (attempt {attempt})")
                await asyncio.sleep(wait)
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

    print(f"-> @{channel}", flush=True)

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
            post_url = link_el.get("href") if link_el else f"https://t.me/{channel}"

            results.append({
                "channel":     channel,
                "channel_url": f"https://t.me/{channel}",
                "post_id":     post_id,
                "url":         post_url,
                "date":        post_dt.isoformat() if post_dt else None,
                "text": f"[{channel} | {post_dt.strftime('%d.%m.%Y %H:%M') if post_dt else ''}] {post_url}\n{text}",
                "views":       parse_views(msg.select_one(".tgme_widget_message_views")),
                "scraped_at":  datetime.now(timezone.utc).isoformat(),
            })

        if stop:
            break

        oldest_id = extract_post_id(messages[-1])
        if not oldest_id:
            break
        page_url = f"{base_url}?before={oldest_id}"

    print(f"  @{channel}: {len(results)} posts", flush=True)
    return results


async def scrape_channel_safe(
    client: httpx.AsyncClient,
    channel: str,
    cutoff: datetime,
    max_posts: int,
) -> list[dict]:
    try:
        return await scrape_channel(client, channel, cutoff, max_posts)
    except Exception as exc:
        Actor.log.error(f"Error scraping @{channel}: {exc}")
        return []


async def load_history(store) -> list[dict]:
    """Завантажує звіти за останні HISTORY_DAYS днів з KV Store."""
    history = []
    today = datetime.now(timezone.utc).date()

    for days_ago in range(1, HISTORY_DAYS + 1):
        date = today - timedelta(days=days_ago)
        key = f"report_{date.strftime('%Y-%m-%d')}"
        try:
            record = await store.get_value(key)
            if record:
                history.append(record)
                print(f"Loaded history: {key}", flush=True)
        except Exception:
            pass  # Запис не існує — пропускаємо

    print(f"History loaded: {len(history)} days", flush=True)
    return history


async def save_today(store, all_posts: list[dict], channels: list[str]) -> None:
    """Зберігає стислий звіт сьогоднішнього дня в KV Store."""
    today_key = f"report_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"

    # Зберігаємо стислу версію (не повні тексти — економимо місце)
    summary = {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "total_posts": len(all_posts),
        "breakdown": {
            ch: sum(1 for p in all_posts if p["channel"] == ch)
            for ch in channels
        },
        # Перші 150 символів кожного поста для трендового порівняння
        "posts_summary": [
            {
                "channel": p["channel"],
                "url": p["url"],
                "date": p["date"],
                "text_preview": p["text"][:150],
            }
            for p in all_posts
        ],
    }

    await store.set_value(today_key, summary)
    print(f"Saved today: {today_key} ({len(all_posts)} posts)", flush=True)


def build_history_context(history: list[dict]) -> str:
    """Будує текстовий контекст з історії для передачі в OpenAI."""
    if not history:
        return "Історія відсутня — перший день моніторингу."

    lines = []
    for record in sorted(history, key=lambda x: x.get("date", ""), reverse=True):
        date = record.get("date", "невідомо")
        total = record.get("total_posts", 0)
        breakdown = record.get("breakdown", {})

        # Топ-5 найактивніших каналів того дня
        top_channels = sorted(breakdown.items(), key=lambda x: x[1], reverse=True)[:5]
        top_str = ", ".join(f"{ch}:{cnt}" for ch, cnt in top_channels)

        lines.append(f"{date}: {total} постів | топ каналів: {top_str}")

    return "\n".join(lines)


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
                print(f"Make.com webhook OK (HTTP {r.status_code})", flush=True)
                return True
            else:
                Actor.log.warning(f"Make.com HTTP {r.status_code} (attempt {attempt}): {r.text[:200]}")
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            Actor.log.warning(f"Webhook error attempt {attempt}: {exc}")

        if attempt < MAX_RETRIES:
            await asyncio.sleep(WEBHOOK_RETRY_DELAY * attempt)

    print("WEBHOOK FAILED", flush=True)
    return False


async def main():
    global _semaphore

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
        print(f"Channels: {len(channels)} | window: {hours_back}h | concurrent: {CONCURRENT_CHANNELS}", flush=True)

        _semaphore = asyncio.Semaphore(CONCURRENT_CHANNELS)

        # Відкриваємо KV Store і завантажуємо історію
        store = await Actor.open_key_value_store(name="osint-belarus-history")
        history = await load_history(store)
        history_context = build_history_context(history)

        all_posts: list[dict] = []

        async with httpx.AsyncClient() as client:
            for i in range(0, len(channels), CONCURRENT_CHANNELS):
                batch = channels[i:i + CONCURRENT_CHANNELS]
                print(f"Batch {i//CONCURRENT_CHANNELS + 1}: {batch}", flush=True)

                tasks = [
                    scrape_channel_safe(client, ch, cutoff, max_posts)
                    for ch in batch
                ]
                results = await asyncio.gather(*tasks)

                for posts in results:
                    if posts:
                        await Actor.push_data(posts)
                    all_posts.extend(posts)

                if i + CONCURRENT_CHANNELS < len(channels):
                    await asyncio.sleep(random.uniform(2.0, 4.0))

        print(f"Scraping done. Total posts: {len(all_posts)}", flush=True)

        # Зберігаємо сьогоднішній звіт в KV Store
        await save_today(store, all_posts, channels)

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
                # Новий блок — історія для трендового аналізу
                "history_context": history_context,
                "history_days_available": len(history),
            }
            async with httpx.AsyncClient() as client:
                await send_to_make(client, webhook_url, payload)
        elif not all_posts:
            Actor.log.warning("No posts collected — webhook not sent.")

        print("Done.", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
