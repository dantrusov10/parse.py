import json
import os
import random
import re
import urllib.request
from datetime import datetime
from pb_client import upsert_article, get_token, slugify, fetch_latest_articles, fetch_all_articles

VERCEL_URL = os.getenv('VERCEL_URL', 'https://newlevelcrm-landing.vercel.app/api/write')
WRITER_SECRET = os.getenv('WRITER_SECRET', 'newlevel2025')
NEWS_JSON_PATH = os.getenv('NEWS_JSON_PATH', '/var/www/nwlvl/news.json')

TOPICS = [
    ('IT-продажи', 'Как увеличить конверсию в IT-продажах с помощью CRM'),
    ('ИИ', 'Как искусственный интеллект меняет B2B продажи в 2025 году'),
    ('Тендеры', 'Как выигрывать тендеры на IT-решения: практическое руководство'),
    ('Маркетинг', 'Контент-маркетинг для IT-компаний: что работает в 2025 году'),
    ('IT-продажи', 'Pipeline management: как не терять сделки на каждом этапе воронки'),
    ('ИИ', 'Автоматизация отдела продаж: с чего начать и как не ошибиться'),
    ('Маркетинг', 'Account-based marketing для IT-продаж: теория и практика'),
    ('IT-продажи', 'CRM для системных интеграторов: на что обратить внимание при выборе'),
    ('Тендеры', 'Закупки по 44-ФЗ и 223-ФЗ: как IT-компании найти своих клиентов'),
    ('IT-продажи', 'Как сократить цикл сделки в B2B IT с 6 месяцев до 2'),
    ('Маркетинг', 'Как IT-вендору выстроить партнёрскую сеть с нуля'),
    ('ИИ', 'ИИ-ассистенты в корпоративных продажах: сравнение и кейсы'),
    ('IT-продажи', 'Работа с возражениями в IT-продажах: скрипты и техники'),
    ('Маркетинг', 'Как использовать LinkedIn для IT-продаж в 2025 году'),
    ('Тендеры', 'Тендерный отдел в IT-компании: когда создавать и как выстроить'),
]


def write_news_json_snapshot(items):
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
    try:
        latest = fetch_latest_articles(limit=30, token=token)
    except Exception:
        latest = []

    recent_titles = [a.get('title', '') for a in latest[:10] if a.get('title')]
    available = [t for t in TOPICS if t[1] not in recent_titles] or TOPICS
    cat, title = random.choice(available)

    print(f'Генерируем: {title}')

    body = json.dumps({'topic': title, 'category': cat, 'secret': WRITER_SECRET}).encode('utf-8')
    req = urllib.request.Request(VERCEL_URL, data=body, headers={'Content-Type': 'application/json'})
    resp = urllib.request.urlopen(req, timeout=120)
    result = json.loads(resp.read())
    content = result.get('content', '')

    if not content:
        print('Ошибка: пустой ответ')
        return

    plain = re.sub(r'<[^>]+>', ' ', content)
    plain = re.sub(r'\s+', ' ', plain).strip()
    excerpt = (plain[:220] + '…') if len(plain) > 220 else plain

    article = {
        'title': title,
        'slug': 'ai-' + slugify(title),
        'excerpt': excerpt,
        'content': content,
        'date': datetime.utcnow().isoformat(),
        'status': 'published',
        'is_featured': True,
        'robots': 'index,follow',
        'seo_title': title[:70],
        'seo_description': excerpt[:180],
    }

    saved = upsert_article(article, token=token)
    print('PB OK:', saved.get('id'))

    try:
        latest = fetch_all_articles(token=token, per_page=200)
        write_news_json_snapshot(latest)
        print('news.json snapshot updated:', NEWS_JSON_PATH)
    except Exception as e:
        print('Snapshot error:', e)

    print(f'OK — статья записана в PB')


if __name__ == '__main__':
    main()
