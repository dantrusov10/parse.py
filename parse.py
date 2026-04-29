import json
import os
import re
import urllib.request
import xml.etree.ElementTree as ET
from pb_client import get_token, upsert_article, fetch_all_articles

SOURCES = [
    ('https://habr.com/ru/rss/hub/sales/all/', 'Habr.com', 'IT-продажи'),
    ('https://habr.com/ru/rss/hub/crm/all/', 'Habr.com', 'IT-продажи'),
    ('https://habr.com/ru/rss/hub/it_management/all/', 'Habr.com', 'IT-продажи'),
    ('https://habr.com/ru/rss/hub/artificial_intelligence/all/', 'Habr.com', 'ИИ'),
    ('https://habr.com/ru/rss/hub/machine_learning/all/', 'Habr.com', 'ИИ'),
    ('https://habr.com/ru/rss/hub/product_management/all/', 'Habr.com', 'Маркетинг'),
    ('https://habr.com/ru/rss/hub/marketing/all/', 'Habr.com', 'Маркетинг'),
    ('https://habr.com/ru/rss/hub/startup/all/', 'Habr.com', 'Маркетинг'),
    ('https://vc.ru/rss/all', 'VC.ru', 'Маркетинг'),
    ('https://www.cnews.ru/inc/rss/news.xml', 'CNews', 'IT-продажи'),
    ('https://rssexport.rbc.ru/rbcnews/news/20/full.rss', 'RBC', 'IT-продажи'),
    ('https://lenta.ru/rss/news', 'Lenta.ru', 'Маркетинг'),
    ('https://ria.ru/export/rss2/archive/index.xml', 'РИА Новости', 'Маркетинг'),
    ('https://www.kommersant.ru/RSS/news.xml', 'Коммерсант', 'Маркетинг'),
]

NEWS_JSON_PATH = os.getenv('NEWS_JSON_PATH', '/var/www/nwlvl/news.json')
ITEMS_PER_SOURCE = int(os.getenv('ITEMS_PER_SOURCE', '5'))


def strip_html(text: str) -> str:
    return re.sub('<[^>]+>', '', text or '')


def parse_feed(url, src, cat):
    out = []
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    data = urllib.request.urlopen(req, timeout=15).read()
    root = ET.fromstring(data)
    for item in root.findall('.//item')[:ITEMS_PER_SOURCE]:
        title = (item.findtext('title', '') or '').strip()
        link = (item.findtext('link', '') or '').strip()
        desc = strip_html(item.findtext('description', ''))[:220].strip()
        date = (item.findtext('pubDate', '') or '').strip()
        if title and link:
            out.append({
                'title': title,
                'url': link,
                'excerpt': desc,
                'date': date,
                'src': src,
                'cat': cat,
                'is_featured': True,
            })
    return out


def write_news_json_snapshot(items):
    if not NEWS_JSON_PATH:
        return
    simplified = []
    for x in items:
        simplified.append({
            'title': x.get('title'),
            'url': x.get('url'),
            'excerpt': x.get('excerpt'),
            'date': x.get('published_at') or x.get('date'),
            'src': x.get('src', 'NewLevel CRM'),
            'cat': x.get('cat', 'IT-продажи'),
            'body': x.get('content') or x.get('body'),
        })
    os.makedirs(os.path.dirname(NEWS_JSON_PATH), exist_ok=True)
    with open(NEWS_JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(simplified, f, ensure_ascii=False)


def main():
    token = get_token()
    seen = set()
    parsed = []

    for url, src, cat in SOURCES:
        try:
            for article in parse_feed(url, src, cat):
                if article['url'] in seen:
                    continue
                seen.add(article['url'])
                parsed.append(article)
        except Exception as e:
            print('Error:', url, e)

    ok = 0
    for art in parsed:
        try:
            upsert_article(art, token=token)
            ok += 1
            print('PB OK:', art['title'][:80])
        except Exception as e:
            print('PB ERROR:', art['title'][:80], e)

    # compatibility snapshot for current site until frontend is switched fully
    try:
        latest = fetch_all_articles(token=token, per_page=200)
        # enrich categories/source from parsed data by slug/url fallback is omitted for simplicity
        write_news_json_snapshot(latest)
        print('news.json snapshot updated:', NEWS_JSON_PATH)
    except Exception as e:
        print('Snapshot error:', e)

    print('DONE', ok, 'articles upserted')


if __name__ == '__main__':
    main()
