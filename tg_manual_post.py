import argparse
from telegram_publisher import publish_manual_post


def main():
    p = argparse.ArgumentParser(description="Manual Telegram post publisher")
    p.add_argument("--title", required=True, help="Post title")
    p.add_argument("--text", required=True, help="Post text")
    p.add_argument("--url", default="", help="Optional button URL")
    args = p.parse_args()

    publish_manual_post(args.title, args.text, args.url)
    print("TG manual post sent")


if __name__ == "__main__":
    main()

