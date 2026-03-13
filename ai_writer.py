import urllib.request
import urllib.parse
import json
import ssl
import random
import os
from datetime import datetime

GIGACHAT_KEY = "MDE5YzQ3MDAtMzU0Yi03ZTYwLWFjMDEtNWI1YTViMzc3YTUzOmZmZmE5ZThjLTNkMTQtNDc4Yy04YzA4LWFiNjU3YjExYTZkYg=="

TOPICS = [
    ("IT-продажи", "Как увеличить конверсию в IT-продажах с помощью CRM-системы"),
    ("ИИ", "Как искусственный интеллект меняет B2B продажи в 2025 году"),
    ("Тендеры", "Как выигрывать тендеры на IT-решения: практическое руководство"),
    ("Маркетинг", "Контент-маркетинг для IT-компаний: что работает в 2025 году"),
    ("IT-продажи", "Pipeline management: как не терять сделки на каждом этапе воронки"),
    ("ИИ", "ГигаЧат в корпоративных продажах: реальные кейсы применения"),
    ("Маркетинг", "Как IT-вендору выстроить партнёрскую сеть с нуля"),
    ("IT-продажи", "CRM для системных интеграторов: на что обратить внимание при выборе"),
    ("Тендеры", "Закупки по 44-ФЗ и 223-ФЗ: как IT-компании найти своих клиентов"),
    ("ИИ", "Автоматизация отдела продаж: с чего начать и как не ошибиться"),
    ("Маркетинг", "Account-based marketing для IT-продаж: теория и практика"),
    ("IT-продажи", "Как сократить цикл сделки в B2B IT с 6 месяцев до 2"),
]

def get_gigachat_token():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    data = urllib.parse.urlencode({"scope": "GIGACHAT_API_PERS"}).encode()
    req = urllib.request.Request(
        "https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
        data=data,
        headers={
            "Authorization": f"Basic {GIGACHAT_KEY}",
            "RqUID": "newlevel-crm-writer",
            "Content-Type": "application/x-www-form-urlencoded"
        }
    )
    resp = urllib.request.urlopen(req, context=ctx, timeout=15)
    return json.loads(resp.read())["access_token"]

def generate_article(token, title, category):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    prompt = f"""Напиши экспертную статью для блога CRM-системы NewLevel CRM.

Тема: {title}
Категория: {category}

Требования:
- Объём: 400-600 слов
- Тон: профессиональный, практичный, без воды
- Структура: короткое введение, 3-4 раздела с подзаголовками, вывод
- Целевая аудитория: руководители IT-компаний, вендоры, системные интеграторы
- Добавь конкретные цифры и примеры
- В конце упомяни что NewLevel CRM помогает решить описанные задачи

Верни только текст статьи в формате HTML (используй <h3> для подзаголовков, <p> для абзацев). Без вводных фраз типа "Вот статья"."""

    body = json.dumps({
        "model": "GigaChat",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1500,
        "temperature": 0.7
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
    )
    resp = urllib.request.urlopen(req, context=ctx, timeout=30)
    result = json.loads(resp.read())
    return result["choices"][0]["message"]["content"]

def main():
    news_path = "/var/www/nwlvl/news.json"

    # Загружаем текущие статьи
    try:
        with open(news_path, "r", encoding="utf-8") as f:
            articles = json.load(f)
    except:
        articles = []

    # Выбираем тему (не повторяем последние 3)
    recent_titles = [a.get("title","") for a in articles[:3] if a.get("src") == "NewLevel CRM"]
    available = [t for t in TOPICS if t[1] not in recent_titles]
    if not available:
        available = TOPICS
    cat, title = random.choice(available)

    print(f"Генерируем статью: {title}")

    try:
        token = get_gigachat_token()
        print("Токен получен")

        content = generate_article(token, title, cat)
        print(f"Статья сгенерирована ({len(content)} символов)")

        # Создаём запись
        article = {
            "title": title,
            "url": None,
            "excerpt": content[:200].replace("<h3>","").replace("</h3>","").replace("<p>","").replace("</p>","") + "...",
            "body": content,
            "date": datetime.now().strftime("%a, %d %b %Y"),
            "src": "NewLevel CRM",
            "cat": cat
        }

        # Добавляем в начало списка
        articles.insert(0, article)

        # Оставляем не более 100 статей
        articles = articles[:100]

        with open(news_path, "w", encoding="utf-8") as f:
            json.dump(articles, f, ensure_ascii=False)

        print(f"OK — статья добавлена. Всего статей: {len(articles)}")

    except Exception as e:
        print(f"Ошибка: {e}")

if __name__ == "__main__":
    main()
