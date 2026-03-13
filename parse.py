import urllib.request
import xml.etree.ElementTree as ET
import json
import re
 
urls = [
    # IT-продажи и CRM
    ('https://habr.com/ru/rss/hub/sales/all/', 'Habr.com', 'IT-продажи'),
    ('https://habr.com/ru/rss/hub/crm/all/', 'Habr.com', 'IT-продажи'),
    ('https://habr.com/ru/rss/hub/b2b/all/', 'Habr.com', 'IT-продажи'),
    # ИИ
    ('https://habr.com/ru/rss/hub/artificial_intelligence/all/', 'Habr.com', 'ИИ'),
    ('https://habr.com/ru/rss/hub/machine_learning/all/', 'Habr.com', 'ИИ'),
    ('https://habr.com/ru/rss/hub/nlp/all/', 'Habr.com', 'ИИ'),
    # Маркетинг и бизнес
    ('https://vc.ru/rss/marketing', 'VC.ru', 'Маркетинг'),
    ('https://vc.ru/rss/sales', 'VC.ru', 'IT-продажи'),
    ('https://vc.ru/rss/ai', 'VC.ru', 'ИИ'),
    # IT новости
    ('https://www.cnews.ru/inc/rss/news.xml', 'CNews', 'IT-продажи'),
    ('https://habr.com/ru/rss/hub/it_management/all/', 'Habr.com', 'IT-продажи'),
    # Тендеры и госзакупки
    ('https://habr.com/ru/rss/hub/gov_it/all/', 'Habr.com', 'Тендеры'),
    # Предпринимательство
    ('https://vc.ru/rss/life', 'VC.ru', 'Маркетинг'),
    ('https://habr.com/ru/rss/hub/startup/all/', 'Habr.com', 'Маркетинг'),
]
 
arts = []
seen = set()
 
for url, src, cat in urls:
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        data = urllib.request.urlopen(req, timeout=10).read()
        root = ET.fromstring(data)
        for item in root.findall('.//item')[:4]:
            title = item.findtext('title', '')
            link = item.findtext('link', '')
            desc = re.sub('<[^>]+>', '', item.findtext('description', ''))[:200]
            date = item.findtext('pubDate', '')[:16]
            if title and link and link not in seen:
                seen.add(link)
                arts.append({'title': title, 'url': link, 'excerpt': desc, 'date': date, 'src': src, 'cat': cat})
    except Exception as e:
        print('Error:', url, e)
 
with open('/var/www/nwlvl/news.json', 'w', encoding='utf-8') as f:
    json.dump(arts, f, ensure_ascii=False)
 
print('OK', len(arts), 'articles saved')
 
