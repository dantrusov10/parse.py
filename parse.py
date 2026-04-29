import json
import os
import re
import html
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
BLOG_PRERENDER_DIR = os.getenv('BLOG_PRERENDER_DIR', '/var/www/nwlvl/blog')
SITE_BASE_URL = os.getenv('SITE_BASE_URL', 'https://nwlvl.ru')

INCLUDE_KEYWORDS = [
    'crm', 'b2b', 'продаж', 'продажи', 'тендер', 'лид', 'воронк', 'ai',
    'ии', 'искусственн', 'автоматизац', 'интегратор', 'дистрибьютор', 'saas',
    'кп', 'коммерческ', 'закупк', 'pipeline', 'конверси', 'маркетинг'
]
EXCLUDE_KEYWORDS = [
    'звезд', 'шоубиз', 'гороскоп', 'дтп', 'убийств', 'войн', 'ракет',
    'обстрел', 'нхл', 'футбол', 'хоккей', 'пожар', 'землетряс', 'криминал'
]


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


def calc_relevance_score(article: dict) -> int:
    text = f"{article.get('title', '')} {article.get('excerpt', '')}".lower()
    score = 0
    for kw in INCLUDE_KEYWORDS:
        if kw in text:
            score += 2
    for kw in EXCLUDE_KEYWORDS:
        if kw in text:
            score -= 4
    if article.get('cat') in ('IT-продажи', 'ИИ', 'Тендеры'):
        score += 2
    return score


def is_quality_article(article: dict) -> bool:
    title = (article.get('title') or '').strip()
    excerpt = (article.get('excerpt') or '').strip()
    if len(title) < 18:
        return False
    if len(excerpt) < 40:
        return False
    return calc_relevance_score(article) >= 2


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


def write_prerender_pages(items):
    if not BLOG_PRERENDER_DIR:
        return
    os.makedirs(BLOG_PRERENDER_DIR, exist_ok=True)
    for x in items:
        slug = (x.get('slug') or '').strip()
        if not slug:
            continue
        title = x.get('seo_title') or x.get('title') or 'Статья'
        description = (x.get('seo_description') or x.get('excerpt') or '').strip()
        robots = (x.get('robots') or 'index,follow').strip()
        canonical = f"{SITE_BASE_URL.rstrip('/')}/blog/{slug}"
        safe_title = html.escape(title, quote=True)
        safe_description = html.escape(description, quote=True)
        safe_canonical = html.escape(canonical, quote=True)
        safe_robots = html.escape(robots, quote=True)
        page_dir = os.path.join(BLOG_PRERENDER_DIR, slug)
        os.makedirs(page_dir, exist_ok=True)
        with open(os.path.join(page_dir, 'index.html'), 'w', encoding='utf-8') as fp:
            fp.write(
                "<!doctype html><html lang=\"ru\"><head>"
                "<meta charset=\"utf-8\"/>"
                "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"/>"
                f"<title>{safe_title} — NewLevel CRM</title>"
                f"<meta name=\"description\" content=\"{safe_description}\"/>"
                f"<meta name=\"robots\" content=\"{safe_robots}\"/>"
                f"<link rel=\"canonical\" href=\"{safe_canonical}\"/>"
                "<meta http-equiv=\"refresh\" content=\"0;url=/blog-post.html?slug=" + html.escape(slug, quote=True) + "\"/>"
                "</head><body></body></html>"
            )


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
                if not is_quality_article(article):
                    continue
                parsed.append(article)
        except Exception as e:
            print('Error:', url, e)

    parsed.sort(key=calc_relevance_score, reverse=True)

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
        write_news_json_snapshot(latest)
        write_prerender_pages(latest)
        print('news.json snapshot updated:', NEWS_JSON_PATH)
    except Exception as e:
        print('Snapshot error:', e)

    print('DONE', ok, 'articles upserted')


if __name__ == '__main__':
    main()
