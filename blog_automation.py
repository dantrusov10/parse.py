import argparse
import time
from datetime import datetime, timedelta

import ai_writer
import parse as parser_job
from pb_client import get_token, slugify, upsert_article


def run_hourly_parse():
    print("[AUTO] hourly parse started")
    parser_job.main()
    print("[AUTO] hourly parse finished")


def run_daily_ai():
    print("[AUTO] daily AI generation started")
    ai_writer.main()
    print("[AUTO] daily AI generation finished")


def run_manual_publish(title: str, content: str, excerpt: str):
    token = get_token()
    article = {
        "title": title.strip(),
        "slug": slugify(title),
        "excerpt": excerpt.strip() or content[:200],
        "content": content.strip(),
        "status": "published",
        "is_featured": True,
        "robots": "index,follow",
        "seo_title": title[:70],
        "seo_description": (excerpt or content[:180]).strip()[:180],
        "published_at": datetime.utcnow().isoformat(),
    }
    saved = upsert_article(article, token=token)
    print("[AUTO] manual article published:", saved.get("id"), article["slug"])


def run_daemon(ai_hour: int):
    next_parse = datetime.utcnow()
    next_ai = datetime.utcnow().replace(hour=ai_hour, minute=0, second=0, microsecond=0)
    if next_ai <= datetime.utcnow():
        next_ai = next_ai + timedelta(days=1)

    print(f"[AUTO] daemon started, ai_hour_utc={ai_hour}")
    while True:
        now = datetime.utcnow()
        if now >= next_parse:
            try:
                run_hourly_parse()
            except Exception as e:
                print("[AUTO] parse error:", e)
            next_parse = now + timedelta(hours=1)

        if now >= next_ai:
            try:
                run_daily_ai()
            except Exception as e:
                print("[AUTO] ai error:", e)
            next_ai = next_ai + timedelta(days=1)

        time.sleep(20)


def main():
    ap = argparse.ArgumentParser(description="NewLevel blog automation")
    ap.add_argument("--mode", choices=["hourly", "daily-ai", "daemon", "manual"], required=True)
    ap.add_argument("--ai-hour-utc", type=int, default=7)
    ap.add_argument("--title", default="")
    ap.add_argument("--content", default="")
    ap.add_argument("--excerpt", default="")
    args = ap.parse_args()

    if args.mode == "hourly":
        run_hourly_parse()
    elif args.mode == "daily-ai":
        run_daily_ai()
    elif args.mode == "daemon":
        run_daemon(args.ai_hour_utc)
    else:
        if not args.title or not args.content:
            raise SystemExit("--title and --content are required for --mode manual")
        run_manual_publish(args.title, args.content, args.excerpt)


if __name__ == "__main__":
    main()
