Что изменено:
1. parse.py больше не пишет статьи напрямую в news.json как в основное хранилище.
   Теперь он:
   - парсит RSS,
   - upsert-ит статьи в PocketBase CMS -> site_articles,
   - после этого пересобирает /var/www/nwlvl/news.json как временный snapshot для совместимости.

2. ai_writer.py теперь тоже пишет статью в PocketBase CMS -> site_articles,
   а потом пересобирает news.json snapshot.

3. Добавлен pb_client.py с общей логикой:
   - авторизация в cms_users (если заданы PB_EMAIL/PB_PASSWORD)
   - поиск по slug
   - create/update статьи
   - безопасные slug
   - нормализация дат

Как запускать:
- можно как раньше: python3 parse.py и python3 ai_writer.py
- новый orchestrator: python3 blog_automation.py --mode hourly
- ежедневная AI-статья: python3 blog_automation.py --mode daily-ai
- единый daemon (парсинг каждый час + AI раз в день):
  python3 blog_automation.py --mode daemon --ai-hour-utc 7
- ручная публикация:
  python3 blog_automation.py --mode manual --title "Заголовок" --content "<h3>...</h3><p>...</p>" --excerpt "Короткое описание"
- если createRule в site_articles открыт, авторизация не обязательна
- если createRule закрыт, задайте env:
  export PB_EMAIL='admin@example.com'
  export PB_PASSWORD='пароль'

Доп. env:
- PB_URL=https://cms-api.nwlvl.ru
- NEWS_JSON_PATH=/var/www/nwlvl/news.json
- ITEMS_PER_SOURCE=5

Расширение источников:
- Habr sales/crm/ai/ml/product/marketing/it_management/startup
- VC.ru
- CNews
- RBC
- Lenta
- РИА Новости
- Коммерсант
