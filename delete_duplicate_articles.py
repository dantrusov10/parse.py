#!/usr/bin/env python3
"""
Удаляет дубли в site_articles по нормализованному заголовку.
Оставляет самую свежую запись (по published_at/created), удаляет остальные.

Без флага --confirm работает в dry-run режиме.
AI-статьи (slug startswith ai-) не трогает.
"""

from __future__ import annotations

import argparse
import re
import sqlite3
from datetime import datetime

DB_PATH = "/opt/pb-cms/pb_data/data.db"


def normalize_title(value: str) -> str:
    v = (value or "").strip().lower().replace("ё", "е")
    v = re.sub(r"^\s*\[\s*перевод\s*\]\s*[:\-–—\.]?\s*", "", v, flags=re.IGNORECASE)
    v = re.sub(r"[^a-zа-я0-9]+", " ", v, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", v).strip()


def parse_ts(value: str):
    if not value:
        return datetime.min
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return datetime.min


def main() -> None:
    parser = argparse.ArgumentParser(description="Удалить дубли в site_articles по title.")
    parser.add_argument("--confirm", action="store_true", help="выполнить удаление")
    parser.add_argument("--show", type=int, default=40, help="сколько примеров показать")
    args = parser.parse_args()

    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT id, title, slug, published_at, created FROM site_articles WHERE status='published'"
    ).fetchall()

    groups: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        slug = (row["slug"] or "").strip()
        if slug.startswith("ai-"):
            continue
        key = normalize_title(row["title"] or "")
        if len(key) < 12:
            continue
        groups.setdefault(key, []).append(row)

    to_delete: list[tuple[str, str, str, str, str]] = []
    dup_groups = 0
    for _, items in groups.items():
        if len(items) < 2:
            continue
        dup_groups += 1
        ordered = sorted(
            items,
            key=lambda x: (parse_ts(x["published_at"] or x["created"]), x["id"]),
            reverse=True,
        )
        keep = ordered[0]
        for old in ordered[1:]:
            to_delete.append((old["id"], old["slug"], old["title"], keep["id"], keep["slug"]))

    print("published_rows", len(rows))
    print("duplicate_groups", dup_groups)
    print("delete_candidates", len(to_delete))
    for rec in to_delete[: args.show]:
        print("DEL", rec[0], rec[1], "|", (rec[2] or "")[:90], "| keep", rec[3], rec[4])
    if len(to_delete) > args.show:
        print("... and", len(to_delete) - args.show, "more")

    if not args.confirm:
        return

    deleted = 0
    for rec in to_delete:
        con.execute("DELETE FROM site_articles WHERE id = ?", (rec[0],))
        deleted += 1
    con.commit()
    print("deleted", deleted)


if __name__ == "__main__":
    main()

