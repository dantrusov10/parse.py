import urllib.request
import json
import random
from datetime import datetime

GROQ_KEY = "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"

TOPICS = [
    ("IT-продажи", "Как увеличить конверсию в IT-продажах с помощью CRM"),
    ("ИИ", "Как искусственный интеллект меняет B2B продажи в 2025 году"),
    ("Тендеры", "Как выигрывать тендеры на IT-решения: практическое руководство"),
    ("Маркетинг", "Контент-маркетинг для IT-компаний: что работает в 2025 году"),
    ("IT-продажи", "Pipeline management: как не терять сделки на каждом этапе воронки"),
    ("ИИ", "Автоматизация отдела продаж: с чего начать и как не ошибиться"),
    ("Маркетинг", "Account-based marketing для IT-продаж: теория и практика"),
    ("IT-продажи", "CRM для системных интеграторов: на что обратить внимание при выборе"),
    ("Тендеры", "Закупки по 44-ФЗ и 223-ФЗ: как IT-компании найти своих клиентов"),
    ("IT-продажи", "Как сократить цикл сделки в B2B IT с 6 месяцев до 2"),
    ("Маркетинг", "Как IT-вендору выстроить партнёрскую сеть с нуля"),
    ("ИИ", "ГигаЧат и ChatGPT в корпоративных продажах: сравнение и кейсы"),
    ("IT-продажи", "Работа с возражениями в IT-продажах: скрипты и техники"),
    ("Маркетинг", "Как использовать LinkedIn для IT-продаж в 2025 году"),
    ("Тендеры", "Тендерный отдел в IT-компании: когда создавать и как выстроить"),
]

def generate_article(title, category):
    prompt = f"""Напиши экспертную статью для блога CRM-системы NewLevel CRM.

Тема: {title}
Категория: {category}

Требования:
- Объём: 500-700 слов
- Тон: профессиональный, практичный, без воды и канцелярита
- Структура: короткое введение (2-3 предложения), 3-4 раздела с подзаголовками, конкретный вывод
- Целевая аудитория: руководители IT-компаний, вендоры, системные интеграторы
- Добавь конкретные цифры, примеры из практики
- В финальном абзаце упомяни что NewLevel CRM помогает решить описанные задачи
- Пиши живым языком, как опытный практик а не как ChatGPT

Верни только текст статьи в формате HTML: используй <h3> для подзаголовков, <p> для абзацев, <strong> для выделений. Без вводных фраз."""

    body = json.dumps({
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 2000,
        "temperature": 0.75
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {GROQ_KEY}",
            "Content-Type": "application/json"
        }
    )
    resp = urllib.request.urlopen(req, timeout=30)
    result = json.loads(resp.read())
    return result["choices"][0]["message"]["content"]

def main():
    news_path = "/var/www/nwlvl/news.json"

    try:
        with open(news_path, "r", encoding="utf-8") as f:
            articles = json.load(f)
    except:
        articles = []

    recent_titles = [a.get("title","") for a in articles[:5] if a.get("src") == "NewLevel CRM"]
    available = [t for t in TOPICS if t[1] not in recent_titles]
    if not available:
        available = TOPICS
    cat, title = random.choice(available)

    print(f"Генерируем: {title}")

    try:
        content = generate_article(title, cat)
        print(f"Готово ({len(content)} символов)")

        excerpt = content.replace("<h3>","").replace("</h3>","").replace("<p>","").replace("</p>","").replace("<strong>","").replace("</strong>","")[:220] + "..."

        article = {
            "title": title,
            "url": None,
            "excerpt": excerpt,
            "body": content,
            "date": datetime.now().strftime("%a, %d %b %Y"),
            "src": "NewLevel CRM",
            "cat": cat
        }

        articles.insert(0, article)
        articles = articles[:100]

        with open(news_path, "w", encoding="utf-8") as f:
            json.dump(articles, f, ensure_ascii=False)

        print(f"OK — сохранено. Всего статей: {len(articles)}")

    except Exception as e:
        print(f"Ошибка: {e}")

if __name__ == "__main__":
    main()
