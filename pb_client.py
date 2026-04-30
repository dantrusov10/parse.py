import json
import os
import re
import hashlib
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

PB_URL = os.getenv('PB_URL', 'https://cms-api.nwlvl.ru').rstrip('/')
PB_COLLECTION = os.getenv('PB_COLLECTION', 'site_articles')
PB_USER_COLLECTION = os.getenv('PB_USER_COLLECTION', 'cms_users')
PB_EMAIL = os.getenv('PB_EMAIL', '')
PB_PASSWORD = os.getenv('PB_PASSWORD', '')
PB_TIMEOUT = int(os.getenv('PB_TIMEOUT', '30'))

_translit_map = {
    'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e','ж':'zh','з':'z','и':'i','й':'y',
    'к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r','с':'s','т':'t','у':'u','ф':'f',
    'х':'h','ц':'ts','ч':'ch','ш':'sh','щ':'sch','ъ':'','ы':'y','ь':'','э':'e','ю':'yu','я':'ya'
}


def translit(text: str) -> str:
    out = []
    for ch in (text or '').lower():
        out.append(_translit_map.get(ch, ch))
    return ''.join(out)


def slugify(text: str, fallback: str = 'article') -> str:
    s = translit(text or fallback)
    s = re.sub(r'[^a-z0-9]+', '-', s)
    s = re.sub(r'-+', '-', s).strip('-')
    return (s or fallback)[:120]


def slug_from_url(url: str, title: str = '') -> str:
    if url:
        short_hash = hashlib.sha1(url.encode('utf-8')).hexdigest()[:10]
        patterns = [
            r'/articles/(\d+)',
            r'/news/line/(\d{4}-\d{2}-\d{2}_[a-z0-9_\-]+)',
            r'/([0-9]{6,})[-_a-zA-Z0-9]*\?',
            r'/([0-9]{6,})[-_a-zA-Z0-9]*$'
        ]
        for p in patterns:
            m = re.search(p, url)
            if m:
                return slugify(f"imported-{m.group(1)}-{short_hash}")
        path = urllib.parse.urlparse(url).path.strip('/')
        if path:
            return slugify(f"{path.replace('/', '-')}-{short_hash}")
    return slugify(title)


def normalize_date(value: str) -> str:
    if not value:
        return datetime.now(timezone.utc).isoformat()
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        pass
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%a, %d %b %Y', '%a, %d %b %Y %H:%M:%S %z'):
        try:
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat()
        except Exception:
            continue
    return datetime.now(timezone.utc).isoformat()


def pb_request(method: str, path: str, payload=None, token: str = ''):
    url = f'{PB_URL}{path}'
    headers = {'Content-Type': 'application/json', 'User-Agent': 'NewLevel-Parser/1.0'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=PB_TIMEOUT) as resp:
        raw = resp.read().decode('utf-8')
        return json.loads(raw) if raw else {}


def get_token() -> str:
    if not (PB_EMAIL and PB_PASSWORD):
        return ''
    try:
        data = pb_request('POST', f'/api/collections/{PB_USER_COLLECTION}/auth-with-password', {
            'identity': PB_EMAIL,
            'password': PB_PASSWORD,
        })
        return data.get('token', '')
    except Exception as e:
        print('PB auth failed, fallback to unauthenticated mode:', e)
        return ''


def find_article_by_slug(slug: str, token: str = ''):
    flt = urllib.parse.quote(f'slug="{slug}"', safe='')
    data = pb_request('GET', f'/api/collections/{PB_COLLECTION}/records?filter={flt}&perPage=1', token=token)
    items = data.get('items', [])
    return items[0] if items else None


def find_article_by_url(url: str, token: str = ''):
    if not url:
        return None
    flt = urllib.parse.quote(f'canonical_url="{url}"', safe='')
    data = pb_request('GET', f'/api/collections/{PB_COLLECTION}/records?filter={flt}&perPage=1', token=token)
    items = data.get('items', [])
    return items[0] if items else None


def build_article_payload(article: dict) -> dict:
    title = (article.get('title') or 'Без названия').strip()
    excerpt = (article.get('excerpt') or '').strip()
    content = (article.get('body') or article.get('content') or excerpt).strip()
    slug = article.get('slug') or slug_from_url(article.get('url', ''), title)
    return {
        'title': title,
        'slug': slug,
        'status': article.get('status', 'published'),
        'excerpt': excerpt,
        'content': content,
        'published_at': normalize_date(article.get('date') or article.get('published_at') or ''),
        'is_featured': bool(article.get('is_featured', True)),
        'robots': article.get('robots', 'index,follow'),
        'seo_title': (article.get('seo_title') or title)[:70],
        'seo_description': (article.get('seo_description') or excerpt)[:180],
        'canonical_url': article.get('url', '') or article.get('canonical_url', ''),
    }


def upsert_article(article: dict, token: str = ''):
    payload = build_article_payload(article)
    existing = None
    try:
        existing = find_article_by_url(payload.get('canonical_url', ''), token=token)
    except Exception as e:
        print('PB find by URL warning:', e)
    if not existing:
        try:
            existing = find_article_by_slug(payload['slug'], token=token)
        except Exception as e:
            print('PB find by slug warning:', e)
    if existing:
        try:
            return pb_request('PATCH', f'/api/collections/{PB_COLLECTION}/records/{existing["id"]}', payload, token=token)
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
            # Record exists, but update is unavailable by API rules; keep existing as-is.
            print('PB patch 404, keep existing record:', payload.get('slug'))
            return existing
    try:
        return pb_request('POST', f'/api/collections/{PB_COLLECTION}/records', payload, token=token)
    except urllib.error.HTTPError as e:
        if e.code != 400:
            raise
        # Common race/duplicate case: record already exists by slug/canonical_url.
        print('PB create 400, trying to resolve existing record:', payload.get('slug'))
        resolved = None
        try:
            resolved = find_article_by_url(payload.get('canonical_url', ''), token=token)
        except Exception:
            pass
        if not resolved:
            try:
                resolved = find_article_by_slug(payload['slug'], token=token)
            except Exception:
                pass
        if resolved:
            return resolved
        raise


def fetch_latest_articles(limit: int = 100, token: str = ''):
    sort = urllib.parse.quote('-published_at')
    data = pb_request('GET', f'/api/collections/{PB_COLLECTION}/records?sort={sort}&perPage={limit}', token=token)
    return data.get('items', [])


def fetch_all_articles(token: str = '', per_page: int = 200):
    sort = urllib.parse.quote('-published_at')
    page = 1
    all_items = []
    while True:
        data = pb_request('GET', f'/api/collections/{PB_COLLECTION}/records?sort={sort}&perPage={per_page}&page={page}', token=token)
        items = data.get('items', []) or []
        all_items.extend(items)
        total_pages = int(data.get('totalPages', 1) or 1)
        if page >= total_pages or not items:
            break
        page += 1
    return all_items
