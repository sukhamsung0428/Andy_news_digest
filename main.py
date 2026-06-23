#!/usr/bin/env python3
"""Daily news digest -> Email (Physical AI / AI Data Center / Bitcoin)"""

import os
import sys
import ssl
import html
import time
import smtplib
import urllib.parse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
from datetime import datetime, timezone, timedelta

import requests
import feedparser

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
EMAIL_ADDRESS = os.environ.get("EMAIL_ADDRESS", "").strip()
EMAIL_APP_PASSWORD = os.environ.get("EMAIL_APP_PASSWORD", "").strip()
EMAIL_TO = os.environ.get("EMAIL_TO", "").strip() or EMAIL_ADDRESS
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com").strip() or "smtp.gmail.com"
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465").strip() or "465")

# 첫 모델 실패 시 두 번째 모델로 자동 재시도
GEMINI_MODELS = ["gemini-2.5-flash", "gemini-2.5-flash-lite"]
ARTICLES_PER_FEED = 8
CHAR_LIMIT = 800
REQUEST_TIMEOUT = 60

TOPICS = [
    ("Physical AI",     "🤖", '"Physical AI"',     "피지컬 AI"),
    ("AI Data Center",  "🏢", '"AI data center"',  "AI 데이터센터"),
    ("Bitcoin",         "₿",  "Bitcoin",            "비트코인"),
]

KST = timezone(timedelta(hours=9))


def gnews_url(query, lang):
    q = urllib.parse.quote(query)
    if lang == "ko":
        return f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"
    return f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"


def fetch_articles(url, limit):
    feed = feedparser.parse(url)
    items = []
    for entry in feed.entries[:limit]:
        title = (entry.get("title") or "").strip()
        link = (entry.get("link") or "").strip()
        items.append({"title": title, "link": link})
    return items


def call_gemini(prompt, retries=6):
    """여러 모델을 순서대로 시도. 성공 시 (text, None), 실패 시 (None, 사유)."""
    headers = {"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 2048,
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    TRANSIENT = {429, 500, 502, 503, 504}   # 일시적 오류 -> 잠시 쉬고 재시도
    last = "unknown"
    for model in GEMINI_MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        for attempt in range(retries):
            try:
                r = requests.post(url, headers=headers, json=body, timeout=REQUEST_TIMEOUT)
                if r.status_code in TRANSIENT:
                    last = f"{model}: HTTP {r.status_code} (혼잡, 재시도 중)"
                    time.sleep(min(30, 2 ** attempt))
                    continue
                if not r.ok:
                    last = f"{model}: HTTP {r.status_code} {r.text[:120]}"
                    break  # 키/권한 등 치명적 오류 -> 다음 모델로
                data = r.json()
                cand = (data.get("candidates") or [{}])[0]
                parts = (cand.get("content") or {}).get("parts") or []
                texts = [p.get("text", "") for p in parts if p.get("text")]
                if texts:
                    return "".join(texts), None
                last = f"{model}: no text (finishReason={cand.get('finishReason')})"
                break  # 빈 응답 -> 다음 모델로
            except Exception as exc:
                last = f"{model}: {exc}"
                time.sleep(min(20, 2 ** attempt))
    return None, last


def summarize(topic, lang, articles):
    titled = [a for a in articles if a.get("title")]
    if not titled:
        return f"[진단] 기사 {len(articles)}건을 받았지만 제목이 비어 있어 요약 불가 (RSS 파싱 문제)"
    headlines = "\n".join(f"- {a['title']}" for a in titled)
    lang_name = "Korean" if lang == "ko" else "English"
    prompt = (
        f"You are a tech/finance news editor. Below are recent news headlines about "
        f"\"{topic}\" (they may be in English and/or Korean). Write a concise digest in "
        f"{lang_name} of the key developments, in your own words.\nRules:\n"
        f"- STRICTLY under {CHAR_LIMIT} characters.\n- Plain text only, no markdown.\n"
        f"- 3-5 short sentences. Synthesize; do not copy headlines verbatim.\n\n"
        f"Headlines:\n{headlines}"
    )
    text, err = call_gemini(prompt)
    if not text:
        return f"[진단] 요약 실패: {err}"
    text = text.strip()
    if len(text) > CHAR_LIMIT:
        text = text[:CHAR_LIMIT].rsplit(" ", 1)[0].rstrip() + "…"
    return text


def build_topic_html(topic, emoji, en_sum, ko_sum, links):
    links_html = ""
    if links:
        items = "".join(
            f'<li style="margin:2px 0;"><a href="{html.escape(l)}" '
            f'style="color:#2563eb;text-decoration:none;">{html.escape(l[:70])}…</a></li>'
            for l in links[:4])
        links_html = (
            '<p style="margin:14px 0 4px;font-size:13px;color:#6b7280;">🔗 관련 기사</p>'
            f'<ul style="margin:0;padding-left:18px;font-size:13px;">{items}</ul>')
    return f"""
    <div style="margin:0 0 26px;padding:18px 20px;border:1px solid #e5e7eb;
                border-radius:12px;background:#ffffff;">
      <h2 style="margin:0 0 14px;font-size:19px;color:#111827;">{emoji} {html.escape(topic)}</h2>
      <p style="margin:0 0 4px;font-weight:600;font-size:14px;color:#374151;">🇰🇷 한국어</p>
      <p style="margin:0 0 16px;font-size:14px;line-height:1.6;color:#1f2937;
                white-space:pre-wrap;">{html.escape(ko_sum)}</p>
      <p style="margin:0 0 4px;font-weight:600;font-size:14px;color:#374151;">🇺🇸 English</p>
      <p style="margin:0;font-size:14px;line-height:1.6;color:#1f2937;
                white-space:pre-wrap;">{html.escape(en_sum)}</p>
      {links_html}
    </div>"""


def build_email_html(date_str, sections):
    body = "".join(sections)
    return f"""<!DOCTYPE html><html><body style="margin:0;padding:0;background:#f3f4f6;">
    <div style="max-width:680px;margin:0 auto;padding:24px 16px;font-family:
                -apple-system,'Segoe UI',Roboto,'Apple SD Gothic Neo',sans-serif;">
      <h1 style="margin:0 0 4px;font-size:22px;color:#111827;">📰 News Digest</h1>
      <p style="margin:0 0 22px;font-size:14px;color:#6b7280;">{date_str}</p>
      {body}
      <p style="margin:8px 0 0;font-size:12px;color:#9ca3af;">
        자동 생성된 다이제스트 · Physical AI · AI Data Center · Bitcoin</p>
    </div></body></html>"""


def send_email(subject, html_body):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = formataddr(("News Digest", EMAIL_ADDRESS))
    msg["To"] = EMAIL_TO
    msg.attach(MIMEText("HTML 메일입니다. HTML 보기를 지원하는 앱에서 열어주세요.", "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context, timeout=REQUEST_TIMEOUT) as server:
            server.login(EMAIL_ADDRESS, EMAIL_APP_PASSWORD)
            server.sendmail(EMAIL_ADDRESS, [EMAIL_TO], msg.as_string())
        return True
    except Exception as exc:
        print(f"  ! Email error: {exc}", file=sys.stderr)
        return False


def main():
    missing = [k for k, v in {
        "GEMINI_API_KEY": GEMINI_API_KEY,
        "EMAIL_ADDRESS": EMAIL_ADDRESS,
        "EMAIL_APP_PASSWORD": EMAIL_APP_PASSWORD,
    }.items() if not v]
    if missing:
        print(f"Missing environment variables: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    date_str = datetime.now(KST).strftime("%Y-%m-%d (%a)")
    sections = []
    for topic, emoji, en_q, ko_q in TOPICS:
        print(f"Processing: {topic}")
        en_articles = fetch_articles(gnews_url(en_q, "en"), ARTICLES_PER_FEED)
        ko_articles = fetch_articles(gnews_url(ko_q, "ko"), ARTICLES_PER_FEED)
        print(f"  fetched: en={len(en_articles)} ko={len(ko_articles)}")
        all_articles = en_articles + ko_articles
        en_sum = summarize(topic, "en", all_articles)
        ko_sum = summarize(topic, "ko", all_articles)
        links = [a["link"] for a in (en_articles[:2] + ko_articles[:2]) if a["link"]]
        sections.append(build_topic_html(topic, emoji, en_sum, ko_sum, links))
        time.sleep(1)

    subject = f"📰 News Digest — {date_str}"
    ok = send_email(subject, build_email_html(date_str, sections))
    print(f"-> email {'sent' if ok else 'FAILED'} to {EMAIL_TO}")
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
