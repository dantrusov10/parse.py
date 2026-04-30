#!/usr/bin/env python3
"""
Удаляет из PocketBase коллекции site_articles записи со slug, начинающимся с 'ai-'
(автогенерация блога; на сайте они показываются как «Команда NewLevel CRM»).

Переменные окружения (как у парсера):
  PB_URL, PB_COLLECTION, PB_USER_COLLECTION, PB_EMAIL, PB_PASSWORD

Запуск:
  python3 delete_ai_blog_articles.py           # только список и счётчик
  python3 delete_ai_blog_articles.py --confirm # удалить

После удаления на сервере перезапустите снимок ленты, например:
  /bin/bash /usr/local/bin/parse-news-run.sh
или дождитесь следующего часового запуска парсера.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

PB_URL = os.getenv("PB_URL", "https://cms-api.nwlvl.ru").rstrip("/")
PB_COLLECTION = os.getenv("PB_COLLECTION", "site_articles")
PB_USER_COLLECTION = os.getenv("PB_USER_COLLECTION", "cms_users")
PB_EMAIL = os.getenv("PB_EMAIL", "")
PB_PASSWORD = os.getenv("PB_PASSWORD", "")
PB_TIMEOUT = int(os.getenv("PB_TIMEOUT", "30"))


def pb_request(method: str, path: str, payload=None, token: str = "") -> dict:
    url = f"{PB_URL}{path}"
    headers = {"Content-Type": "application/json", "User-Agent": "NewLevel-Parser/delete-ai/1.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=PB_TIMEOUT) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def get_token() -> str:
    if not (PB_EMAIL and PB_PASSWORD):
        print("Задайте PB_EMAIL и PB_PASSWORD", file=sys.stderr)
        sys.exit(1)
    data = pb_request(
        "POST",
        f"/api/collections/{PB_USER_COLLECTION}/auth-with-password",
        {"identity": PB_EMAIL, "password": PB_PASSWORD},
    )
    t = data.get("token", "")
    if not t:
        print("Не удалось получить токен PocketBase", file=sys.stderr)
        sys.exit(1)
    return t


def fetch_all_records(token: str) -> list[dict]:
    page = 1
    per_page = 200
    out: list[dict] = []
    while True:
        path = f"/api/collections/{PB_COLLECTION}/records?sort=-published_at&perPage={per_page}&page={page}"
        data = pb_request("GET", path, token=token)
        items = data.get("items") or []
        out.extend(items)
        total_pages = int(data.get("totalPages") or 1)
        if page >= total_pages or not items:
            break
        page += 1
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Удалить статьи блога с slug ai-* (автоген).")
    ap.add_argument("--confirm", action="store_true", help="реально удалить записи в PB")
    args = ap.parse_args()

    token = get_token()
    all_items = fetch_all_records(token)
    targets = [x for x in all_items if str(x.get("slug") or "").startswith("ai-")]

    print(f"Всего записей в {PB_COLLECTION}: {len(all_items)}")
    print(f"К удалению (slug начинается с ai-): {len(targets)}")
    for x in targets[:50]:
        print(" -", x.get("slug"), "|", (x.get("title") or "")[:70])
    if len(targets) > 50:
        print(f" ... и ещё {len(targets) - 50}")

    if not args.confirm:
        print("\nДля удаления запустите с флагом --confirm")
        return

    deleted = 0
    for x in targets:
        rid = x.get("id")
        if not rid:
            continue
        try:
            pb_request("DELETE", f"/api/collections/{PB_COLLECTION}/records/{rid}", token=token)
            deleted += 1
        except urllib.error.HTTPError as e:
            print("HTTPError", rid, e.code, file=sys.stderr)
        except Exception as e:
            print("Error", rid, e, file=sys.stderr)
    print(f"Удалено записей: {deleted}")


if __name__ == "__main__":
    main()
