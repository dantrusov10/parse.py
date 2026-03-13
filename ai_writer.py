import urllib.request
import json
import random
from datetime import datetime

VERCEL_URL = "https://newlevelcrm-landing.vercel.app/api/write"
WRITER_SECRET = "newlevel2025"

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
        body = json.dumps({"topic": title, "category": cat, "secret": WRITER_SECRET}).encode("utf-8")
        req = urllib.request.Request(
            VERCEL_URL,
            data=body,
            headers={"Content-Type": "application/json"}
        )
        resp = urllib.request.urlopen(req, timeout=30)
        result = json.loads(resp.read())
        content = result.get("content", "")

        if not content:
            print("Ошибка: пустой ответ")
            return

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
