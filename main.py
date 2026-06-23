#!/usr/bin/env python3
"""
Daily news digest -> Telegram
Topics: Physical AI / AI Data Center / Bitcoin
For each topic it fetches Google News RSS in English AND Korean, asks Gemini
(free tier) to write a <=800-character summary per language, and posts the
result to a Telegram chat.

Required environment variables (set them as GitHub Actions secrets):
  GEMINI_API_KEY       - from Google AI Studio (free)
  TELEGRAM_BOT_TOKEN   - from @BotFather
  TELEGRAM_CHAT_ID     - your chat / user id
"""

import os
import sys
import html
import time
import urllib.parse
from datetime import datetime, timezone, timedelta

import requests
import feedparser

# ----------------------------- Configuration -----------------------------
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

GEMINI_MODEL = "gemini-2.5-flash"   # stable free-tier alias (verified Q2 2026)
ARTICLES_PER_FEED = 8               # how many recent headlines feed each summary
CHAR_LIMIT = 800                    # max characters per summary
REQUEST_TIMEOUT = 60

# Each topic: (display name, emoji, English query, Korean query)
# To add/remove topics, just edit this list.
TOPICS = [
    ("Physical AI",     "🤖", '"Physical AI"',     "피지컬 AI"),
    ("AI Data Center",  "🏢", '"AI data center"',  "AI 데이터센터"),
    ("Bitcoin",         "₿",  "Bitcoin",            "비트코인"),
]

KST = timezone(timedelta(hours=9))


# ------------------------------- Helpers ---------------------------------
def gnews_url(query: str, lang: str) -> str:
    """Build a Google News RSS search URL for a keyword query."""
    q = urllib.parse.quote(query)
    if lang == "ko":
        return f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"
    return f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"


def fetch_articles(url: str, limit: int):
    """Return a list of {title, link, source} dicts from an RSS feed."""
    feed = feedparser.parse(url)
    items = []
    for entry in feed.entries[:limit]:
        title = (entry.get("title") or "").strip()
        link = (entry.get("link") or "").strip()
        source = ""
        src = entry.get("source")
        if isinstance(src, dict):
            source = src.get("title", "")
        items.append({"title": title, "link": link, "source": source})
    return items


def call_gemini(prompt: str, retries: int = 4):
    """Call Gemini generateContent and return the text, or None on failure."""
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/"
        f"models/{GEMINI_MODEL}:generateContent"
    )
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY,
    }
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 1024},
    }
    for attempt in range(retries):
        try:
            r = requests.post(url, headers=headers, json=body,
                              timeout=REQUEST_TIMEOUT)
            if r.status_code == 429:                     # rate limited -> back off
                time.sleep(min(60, 2 ** attempt))
                continue
            r.raise_for_status()
            data = r.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as exc:                         # noqa: BLE001
            if attempt == retries - 1:
                print(f"  ! Gemini error: {exc}", file=sys.stderr)
                return None
            time.sleep(2 ** attempt)
    return None


def summarize(topic: str, lang: str, articles: list):
    """Summarize a topic's headlines into <=CHAR_LIMIT characters."""
    headlines = "\n".join(f"- {a['title']}" for a in articles if a["title"])
    if not headlines:
        return None
    lang_name = "Korean" if lang == "ko" else "English"
    prompt = (
        f"You are a tech/finance news editor. Below are recent news headlines "
        f"about \"{topic}\". Write a concise digest in {lang_name} of the key "
        f"developments and themes, in your own words.\n"
        f"Rules:\n"
        f"- STRICTLY under {CHAR_LIMIT} characters.\n"
        f"- Plain text only: no markdown, no headers, no bullet symbols.\n"
        f"- 3-5 short sentences. Synthesize and consolidate; do NOT copy "
        f"headline wording verbatim.\n"
        f"- Focus on what is new and why it matters.\n\n"
        f"Headlines:\n{headlines}"
    )
    text = call_gemini(prompt)
    if not text:
        return None
    text = text.strip()
    if len(text) > CHAR_LIMIT:                           # hard safety truncate
        text = text[:CHAR_LIMIT].rsplit(" ", 1)[0].rstrip() + "…"
    return text


def send_telegram(text: str) -> bool:
    """Send one message to the configured Telegram chat."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        r = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT)
        if not r.ok:
            print(f"  ! Telegram {r.status_code}: {r.text}", file=sys.stderr)
        return r.ok
    except Exception as exc:                             # noqa: BLE001
        print(f"  ! Telegram error: {exc}", file=sys.stderr)
        return False


def build_message(topic, emoji, date_str, en_sum, ko_sum, links):
    parts = [
        f"{emoji} <b>{html.escape(topic)}</b>  ·  {date_str}",
        "",
        "🇺🇸 <b>English</b>",
        html.escape(en_sum),
        "",
        "🇰🇷 <b>한국어</b>",
        html.escape(ko_sum),
    ]
    if links:
        parts += ["", "🔗 " + "  ·  ".join(links[:4])]
    return "\n".join(parts)


# --------------------------------- Main ----------------------------------
def main():
    missing = [k for k, v in {
        "GEMINI_API_KEY": GEMINI_API_KEY,
        "TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
        "TELEGRAM_CHAT_ID": TELEGRAM_CHAT_ID,
    }.items() if not v]
    if missing:
        print(f"Missing environment variables: {', '.join(missing)}",
              file=sys.stderr)
        sys.exit(1)

    date_str = datetime.now(KST).strftime("%Y-%m-%d (%a)")

    for topic, emoji, en_q, ko_q in TOPICS:
        print(f"Processing: {topic}")
        en_articles = fetch_articles(gnews_url(en_q, "en"), ARTICLES_PER_FEED)
        ko_articles = fetch_articles(gnews_url(ko_q, "ko"), ARTICLES_PER_FEED)

        en_sum = summarize(topic, "en", en_articles) \
            or "No recent English articles found."
        ko_sum = summarize(topic, "ko", ko_articles) \
            or "최근 한국어 기사를 찾지 못했습니다."

        links = [a["link"] for a in (en_articles[:2] + ko_articles[:2])
                 if a["link"]]

        message = build_message(topic, emoji, date_str, en_sum, ko_sum, links)
        ok = send_telegram(message)
        print(f"  -> {'sent' if ok else 'FAILED'}")
        time.sleep(1)                                    # be gentle with the API


if __name__ == "__main__":
    main()
