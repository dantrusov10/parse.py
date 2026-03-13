import urllib.request
import xml.etree.ElementTree as ET
import json
import re

urls = [
    'https://habr.com/ru/rss/hub/sales/all/',
    'https://habr.com/ru/rss/hub/crm/all/',
]

arts = []
for url in urls:
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        data = urllib.request.urlopen(req, timeout=10).read()
        root = ET.fromstring(data)
        for item in root.findall('.//item')[:4]:
            title = item.findtext('title', '')
            link = item.findtext('link', '')
            desc = re.sub('<[^>]+>', '', item.findtext('description', ''))[:200]
            date = item.findtext('pubDate', '')[:16]
            if title and link:
                arts.append({'title': title, 'url': link, 'excerpt': desc, 'date': date, 'src': 'Habr.com', 'cat': 'IT-продажи'})
    except Exception as e:
        print('Error:', url, e)

with open('/var/www/nwlvl/news.json', 'w', encoding='utf-8') as f:
    json.dump(arts, f, ensure_ascii=False)

print('OK', len(arts), 'articles saved')
