import json
import os
import re
import html
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from pb_client import get_token, upsert_article, fetch_all_articles

SOURCES = [
    ('https://habr.com/ru/rss/hub/sales/all/', 'Habr.com', 'IT-продажи'),
    ('https://habr.com/ru/rss/hub/crm/all/', 'Habr.com', 'IT-продажи'),
    ('https://habr.com/ru/rss/news/', 'Habr.com', 'IT-продажи'),
    ('https://habr.com/ru/rss/hub/artificial_intelligence/all/', 'Habr.com', 'ИИ'),
    ('https://habr.com/ru/rss/hub/machine_learning/all/', 'Habr.com', 'ИИ'),
    ('https://habr.com/ru/rss/all/all/?fl=ru', 'Habr.com', 'Маркетинг'),
    ('https://vc.ru/rss/all', 'VC.ru', 'Маркетинг'),
    ('https://www.cnews.ru/inc/rss/news.xml', 'CNews', 'IT-продажи'),
    ('https://www.vedomosti.ru/rss/news', 'Ведомости', 'Маркетинг'),
    ('https://www.it-world.ru/rss/news.xml', 'IT World', 'IT-продажи'),
    ('https://lenta.ru/rss/news', 'Lenta.ru', 'Маркетинг'),
    ('https://ria.ru/export/rss2/archive/index.xml', 'РИА Новости', 'Маркетинг'),
    ('https://www.kommersant.ru/RSS/news.xml', 'Коммерсант', 'Маркетинг'),
]

NEWS_JSON_PATH = os.getenv('NEWS_JSON_PATH', '/var/www/nwlvl/news.json')
ITEMS_PER_SOURCE = int(os.getenv('ITEMS_PER_SOURCE', '5'))
BLOG_PRERENDER_DIR = os.getenv('BLOG_PRERENDER_DIR', '/var/www/nwlvl/blog')
SITE_BASE_URL = os.getenv('SITE_BASE_URL', 'https://nwlvl.ru')
BLOG_SITEMAP_PATH = os.getenv('BLOG_SITEMAP_PATH', '/var/www/nwlvl/blog-sitemap.xml')
PING_SITEMAP_URLS = os.getenv(
    'PING_SITEMAP_URLS',
    'https://yandex.ru/ping?sitemap={sitemap},https://www.google.com/ping?sitemap={sitemap}'
)

INCLUDE_KEYWORDS = [
    'crm', 'b2b', 'продаж', 'продажи', 'тендер', 'лид', 'воронк', 'ai',
    'ии', 'искусственн', 'автоматизац', 'интегратор', 'дистрибьютор', 'saas',
    'кп', 'коммерческ', 'закупк', 'pipeline', 'конверси', 'маркетинг'
]
EXCLUDE_KEYWORDS = [
    'звезд', 'шоубиз', 'гороскоп', 'дтп', 'убийств', 'войн', 'ракет',
    'обстрел', 'нхл', 'футбол', 'хоккей', 'пожар', 'землетряс', 'криминал'
]

CATEGORY_RULES = {
    'Тендеры': {
        'phrases': [
            '44-фз', '223-фз', 'госзакупк', 'гос закупк', 'тендерн',
            'конкурсн процедур', 'электронная площадк', 'закупочная процедур',
            'техническое задани', 'тендерная документац', 'банковская гаранти',
            'обеспечение заявк', 'обеспечение исполнени', 'победитель закупки',
            'гк ростех', 'контур.закупки', 'zakupki.gov.ru'
        ],
        'words': [
            'тендер', 'закупк', 'аукцион', 'конкурс', 'котиров', 'фз-44',
            'фз-223', 'заказчик', 'поставщик', 'лот', 'эцп', 'рнп'
        ]
    },
    'ИИ': {
        'phrases': [
            'искусственный интеллект', 'машинное обучение', 'нейронн', 'llm',
            'large language model', 'генеративн', 'prompt engineering',
            'ai-ассистент', 'ai ассистент', 'ai copilot', 'computer vision',
            'natural language processing', 'nlp', 'предиктивная аналитика',
            'рекомендательная система'
        ],
        'words': [
            'ии', 'ai', 'ml', 'gpt', 'модель', 'автоматизац', 'алгоритм',
            'инференс', 'fine-tuning', 'файнтюнинг'
        ]
    },
    'Маркетинг': {
        'phrases': [
            'контент-маркетинг', 'performance marketing', 'demand generation',
            'лидогенерац', 'email-маркетинг', 'abm', 'account based marketing',
            'unit-экономик', 'go-to-market', 'gtm стратегия', 'продуктовый маркетинг',
            'воронка маркетинга', 'retention', 'churn', 'cac', 'ltv'
        ],
        'words': [
            'маркетинг', 'бренд', 'аудитория', 'позиционирован', 'конверси',
            'трафик', 'контент', 'охват', 'креатив', 'вебинар', 'кампан'
        ]
    },
    'IT-продажи': {
        'phrases': [
            'b2b продажи', 'корпоративные продажи', 'отдел продаж',
            'pipeline management', 'sales pipeline', 'sales ops',
            'crm-система', 'crm система', 'коммерческое предложени',
            'цикл сделки', 'win rate', 'sales forecast', 'управление сделк',
            'квалификация лида', 'длинные сделки'
        ],
        'words': [
            'crm', 'продаж', 'лид', 'сделк', 'воронк', 'клиент', 'аккаунт',
            'b2b', 'saas', 'kpi', 'кп', 'пресейл', 'upsell', 'cross-sell',
            'интегратор', 'дистрибьютор', 'вендор'
        ]
    },
}


def strip_html(text: str) -> str:
    return re.sub('<[^>]+>', '', text or '')


def normalize_whitespace(text: str) -> str:
    return re.sub(r'\s+', ' ', (text or '')).strip()


def extract_rss_content_html(item) -> str:
    # Try content:encoded first (most RSS feeds keep longer article body there).
    content_node = item.find('{http://purl.org/rss/1.0/modules/content/}encoded')
    if content_node is not None and (content_node.text or '').strip():
        return content_node.text or ''
    # Fallback to description text
    return item.findtext('description', '') or ''


def build_body_from_rss(item) -> str:
    raw_html = extract_rss_content_html(item)
    text = strip_html(html.unescape(raw_html))
    text = normalize_whitespace(text)
    if not text:
        return ''
    # Keep more material for internal blog pages, but avoid huge blobs.
    text = text[:6000]
    parts = [x.strip() for x in re.split(r'(?<=[.!?])\s+', text) if x.strip()]
    chunks = []
    buf = []
    cur_len = 0
    for p in parts:
        if cur_len + len(p) > 700 and buf:
            chunks.append(' '.join(buf))
            buf = [p]
            cur_len = len(p)
        else:
            buf.append(p)
            cur_len += len(p) + 1
    if buf:
        chunks.append(' '.join(buf))
    chunks = chunks[:8]
    return ''.join(f'<p>{html.escape(c)}</p>' for c in chunks)


def parse_feed(url, src, cat):
    out = []
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    data = urllib.request.urlopen(req, timeout=15).read()
    root = ET.fromstring(data)
    for item in root.findall('.//item')[:ITEMS_PER_SOURCE]:
        title = (item.findtext('title', '') or '').strip()
        link = (item.findtext('link', '') or '').strip()
        full_text = normalize_whitespace(strip_html(item.findtext('description', '')))
        desc = full_text[:380].strip()
        if len(full_text) > 380:
            desc += '…'
        body = build_body_from_rss(item)
        date = (item.findtext('pubDate', '') or '').strip()
        if title and link:
            out.append({
                'title': title,
                'url': link,
                'excerpt': desc,
                'body': body,
                'date': date,
                'src': src,
                'cat': cat,
                'is_featured': True,
            })
    return out


def calc_relevance_score(article: dict) -> int:
    text = f"{article.get('title', '')} {article.get('excerpt', '')} {strip_html(article.get('body', ''))}".lower()
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


def score_category(text: str, category: str) -> int:
    rules = CATEGORY_RULES.get(category, {})
    score = 0
    for phrase in rules.get('phrases', []):
        if phrase in text:
            score += 5
    for word in rules.get('words', []):
        if word in text:
            score += 2
    return score


def recategorize_article(article: dict, fallback_cat: str) -> str:
    text = f"{article.get('title', '')} {article.get('excerpt', '')} {strip_html(article.get('body', ''))}".lower()
    ranked = []
    for cat in CATEGORY_RULES.keys():
        ranked.append((cat, score_category(text, cat)))
    ranked.sort(key=lambda x: x[1], reverse=True)
    best_cat, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0
    # Avoid random reassignment on weak signals.
    if best_score < 4 or (best_score - second_score) < 2:
        return fallback_cat
    return best_cat


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
        fallback_cat = x.get('cat') or 'IT-продажи'
        computed_cat = recategorize_article({
            'title': x.get('title') or '',
            'excerpt': x.get('excerpt') or '',
            'body': x.get('content') or x.get('body') or '',
        }, fallback_cat)
        simplified.append({
            'title': x.get('title'),
            'url': x.get('url'),
            'excerpt': x.get('excerpt'),
            'date': x.get('published_at') or x.get('date'),
            'src': x.get('src', 'NewLevel CRM'),
            'cat': computed_cat,
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


def write_blog_sitemap(items):
    if not BLOG_SITEMAP_PATH:
        return
    entries = []
    for x in items:
        slug = (x.get('slug') or '').strip()
        if not slug:
            continue
        loc = f"{SITE_BASE_URL.rstrip('/')}/blog/{slug}"
        lastmod = (x.get('updated') or x.get('published_at') or x.get('created') or '').strip()
        entries.append((loc, lastmod))

    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, lastmod in entries:
        lines.append('  <url>')
        lines.append(f'    <loc>{html.escape(loc)}</loc>')
        if lastmod:
            lines.append(f'    <lastmod>{html.escape(lastmod)}</lastmod>')
        lines.append('    <changefreq>daily</changefreq>')
        lines.append('    <priority>0.8</priority>')
        lines.append('  </url>')
    lines.append('</urlset>')
    os.makedirs(os.path.dirname(BLOG_SITEMAP_PATH), exist_ok=True)
    with open(BLOG_SITEMAP_PATH, 'w', encoding='utf-8') as fp:
        fp.write('\n'.join(lines))


def ping_search_engines(sitemap_url: str):
    raw = [x.strip() for x in PING_SITEMAP_URLS.split(',') if x.strip()]
    for endpoint in raw:
        url = endpoint.replace('{sitemap}', urllib.parse.quote(sitemap_url, safe=':/?&=%'))
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as resp:
                print('PING OK:', url, 'status=', resp.status)
        except Exception as e:
            print('PING WARN:', url, e)


def main():
    token = get_token()
    seen = set()
    parsed = []

    for url, src, fallback_cat in SOURCES:
        try:
            for article in parse_feed(url, src, fallback_cat):
                if article['url'] in seen:
                    continue
                seen.add(article['url'])
                article['cat'] = recategorize_article(article, fallback_cat)
                if not is_quality_article(article):
                    continue
                parsed.append(article)
        except Exception as e:
            print('Error:', url, e)

    parsed.sort(key=calc_relevance_score, reverse=True)

    ok = 0
    cat_counts = {'IT-продажи': 0, 'Маркетинг': 0, 'ИИ': 0, 'Тендеры': 0}
    for art in parsed:
        try:
            upsert_article(art, token=token)
            ok += 1
            if art.get('cat') in cat_counts:
                cat_counts[art['cat']] += 1
            print('PB OK:', art['title'][:80])
        except Exception as e:
            print('PB ERROR:', art['title'][:80], e)

    # compatibility snapshot for current site until frontend is switched fully
    try:
        latest = fetch_all_articles(token=token, per_page=200)
        write_news_json_snapshot(latest)
        write_prerender_pages(latest)
        write_blog_sitemap(latest)
        ping_search_engines(f"{SITE_BASE_URL.rstrip('/')}/sitemap.xml")
        ping_search_engines(f"{SITE_BASE_URL.rstrip('/')}/blog-sitemap.xml")
        print('news.json snapshot updated:', NEWS_JSON_PATH)
    except Exception as e:
        print('Snapshot error:', e)

    print('DONE', ok, 'articles upserted')
    print('CATEGORY DISTRIBUTION:', cat_counts)


if __name__ == '__main__':
    main()
