import base64
import json
import os
import re
import time
import html as html_lib
import urllib.parse
import urllib.request
from datetime import datetime


TELEGRAM_BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
TELEGRAM_CHANNEL = os.getenv("CHANNEL", "").strip()
TG_RELAY_URL = os.getenv("TG_RELAY_URL", "").strip()
TG_RELAY_SECRET = os.getenv("TG_RELAY_SECRET", "").strip()
POST_LIMIT_RAW = os.getenv("POST_LIMIT", "20/day").strip().lower()
MIN_SCORE = int(os.getenv("MIN_SCORE", "6"))
STYLE = os.getenv("STYLE", "Коротко, по делу.").strip()
ENABLE_IMAGES = os.getenv("TG_ENABLE_IMAGES", "1").strip().lower() not in ("0", "false", "no")

IMG_PROVIDER = os.getenv("IMG_PROVIDER", "").strip().lower()
IMG_API_KEY = os.getenv("IMG_API_KEY", "").strip()
IMG_MODEL = os.getenv("IMG_MODEL", "google/gemini-2.5-flash-image-preview").strip()
IMG_FALLBACK_MODELS = [x.strip() for x in os.getenv("IMG_FALLBACK_MODELS", "").split(",") if x.strip()]

SENT_STORE = os.getenv("TELEGRAM_SENT_STORE", "/var/tmp/newlevel_tg_sent.json")
DAILY_STORE = os.getenv("TELEGRAM_DAILY_STORE", "/var/tmp/newlevel_tg_daily.json")


def _load_json(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path: str, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def _normalize_channel(channel: str) -> str:
    c = (channel or "").strip()
    if c.startswith("https://t.me/"):
        c = c.replace("https://t.me/", "@")
    return c


def _is_configured() -> bool:
    return bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHANNEL)


def _daily_limit() -> int:
    m = re.match(r"^\s*(\d+)\s*/\s*day\s*$", POST_LIMIT_RAW)
    if m:
        return int(m.group(1))
    return 20


def _daily_guard_ok() -> bool:
    limit = _daily_limit()
    today = datetime.utcnow().strftime("%Y-%m-%d")
    state = _load_json(DAILY_STORE, {"date": today, "count": 0})
    if state.get("date") != today:
        state = {"date": today, "count": 0}
    if int(state.get("count", 0)) >= limit:
        print(f"TG SKIP: daily limit reached ({limit}/day)")
        return False
    state["count"] = int(state.get("count", 0)) + 1
    _save_json(DAILY_STORE, state)
    return True


def _already_sent(key: str) -> bool:
    data = _load_json(SENT_STORE, {"keys": []})
    return key in set(data.get("keys", []))


def _mark_sent(key: str):
    data = _load_json(SENT_STORE, {"keys": []})
    keys = list(data.get("keys", []))
    if key not in keys:
        keys.append(key)
    # Keep recent 5000 posts only.
    data["keys"] = keys[-5000:]
    _save_json(SENT_STORE, data)


def _tg_api(method: str, payload: dict):
    if TG_RELAY_URL and TG_RELAY_SECRET:
        req = urllib.request.Request(
            TG_RELAY_URL,
            data=json.dumps(
                {
                    "secret": TG_RELAY_SECRET,
                    "method": method,
                    "payload": payload,
                    "botToken": TELEGRAM_BOT_TOKEN,
                },
                ensure_ascii=False,
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
        data = json.loads(raw or "{}")
        if not data.get("ok"):
            raise RuntimeError(f"Telegram relay error ({method}): {data}")
        return data

    token = TELEGRAM_BOT_TOKEN
    url = f"https://api.telegram.org/bot{token}/{method}"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=25) as resp:
        raw = resp.read().decode("utf-8")
    data = json.loads(raw or "{}")
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error ({method}): {data}")
    return data


def _build_caption(article: dict) -> str:
    title = (article.get("title") or "Без заголовка").strip()
    excerpt = (article.get("excerpt") or "").strip()
    excerpt = html_lib.unescape(excerpt).replace("\xa0", " ")
    excerpt = re.sub(r"\s+", " ", excerpt).strip()
    src = (article.get("src") or "Источник").strip()
    cat = (article.get("cat") or "IT-продажи").strip()
    excerpt = excerpt[:360] + ("…" if len(excerpt) > 360 else "")
    commentary = _editor_comment(article)
    return (
        f"<b>{title}</b>\n\n"
        f"{excerpt}\n\n"
        f"<b>Категория:</b> {cat}\n"
        f"<b>Источник:</b> {src}\n\n"
        f"<b>Что это значит на практике:</b> {commentary}"
    )


def _editor_comment(article: dict) -> str:
    cat = (article.get("cat") or "").strip()
    title = (article.get("title") or "").strip().lower()
    if cat == "ИИ":
        return "проверьте, можно ли внедрить это в ваши ежедневные процессы продаж и поддержки без долгого пилота."
    if cat == "Маркетинг":
        return "оцените влияние на лидогенерацию и стоимость привлечения, а не только на охват."
    if cat == "Тендеры":
        return "сверьте требования и сроки заранее: тут чаще всего теряются сделки на этапе подготовки."
    if "crm" in title or "продаж" in title:
        return "ищите, как эта практика сократит цикл сделки и повысит предсказуемость воронки."
    return "разберите, как это применить в вашем процессе уже на этой неделе и какой KPI это должно улучшить."


def _image_prompt(article: dict) -> str:
    title = (article.get("title") or "").strip()
    excerpt = (article.get("excerpt") or "").strip()
    cat = (article.get("cat") or "IT-продажи").strip()
    return (
        "Create a cinematic technology editorial illustration for a Telegram news post. "
        "No text, no logos, no watermark. Blue/cyan space-tech palette, premium B2B SaaS mood. "
        f"Topic category: {cat}. Headline context: {title}. Excerpt context: {excerpt[:220]}."
    )


def _openrouter_generate_image(article: dict) -> str:
    if IMG_PROVIDER != "openrouter" or not IMG_API_KEY:
        return ""
    models = [IMG_MODEL] + IMG_FALLBACK_MODELS
    prompt = _image_prompt(article)
    for model in models:
        try:
            url = "https://openrouter.ai/api/v1/images/generations"
            payload = {"model": model, "prompt": prompt, "size": "1536x1024"}
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {IMG_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://nwlvl.ru",
                    "X-Title": "NewLevel CRM News Bot",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode("utf-8")
            data = json.loads(raw or "{}")
            arr = data.get("data") or []
            if not arr:
                continue
            if arr[0].get("url"):
                return arr[0]["url"]
            if arr[0].get("b64_json"):
                img_bytes = base64.b64decode(arr[0]["b64_json"])
                file_name = f"/var/tmp/newlevel_tg_img_{int(time.time())}.png"
                with open(file_name, "wb") as f:
                    f.write(img_bytes)
                return file_name
        except Exception as e:
            print(f"IMG WARN ({model}):", e)
            continue
    return ""


def _pollinations_fallback_image(article: dict) -> str:
    title = (article.get("title") or "").strip()
    cat = (article.get("cat") or "IT-продажи").strip()
    prompt = (
        "futuristic editorial illustration, dark blue cyber background, "
        "clean composition, no text, no watermark, "
        f"category {cat}, topic {title}"
    )
    return (
        "https://image.pollinations.ai/prompt/"
        + urllib.parse.quote(prompt, safe="")
        + "?width=1536&height=1024&model=flux&nologo=true"
    )


def _read_url_or_path_data(url_or_path: str):
    if not url_or_path:
        return None
    if url_or_path.startswith("http://") or url_or_path.startswith("https://"):
        req = urllib.request.Request(url_or_path, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=40) as resp:
            return resp.read()
    with open(url_or_path, "rb") as f:
        return f.read()


def _send_photo_with_button(caption: str, image_url_or_path: str, read_more_url: str):
    # Telegram Bot API sendPhoto in multipart mode for bytes is harder in stdlib;
    # use URL mode first, fallback to text post if unsupported.
    if image_url_or_path.startswith("http://") or image_url_or_path.startswith("https://"):
        payload = {
            "chat_id": _normalize_channel(TELEGRAM_CHANNEL),
            "photo": image_url_or_path,
            "caption": caption,
            "parse_mode": "HTML",
            "reply_markup": {
                "inline_keyboard": [[{"text": "Читать полностью", "url": read_more_url}]]
            },
        }
        return _tg_api("sendPhoto", payload)
    return None


def publish_article(article: dict, relevance_score: int = 0):
    if not _is_configured():
        return False
    if relevance_score < MIN_SCORE:
        print(f"TG SKIP: score {relevance_score} < {MIN_SCORE}")
        return False
    url = (article.get("url") or "").strip()
    if not url:
        return False
    key = url
    if _already_sent(key):
        return False
    if not _daily_guard_ok():
        return False

    caption = _build_caption(article)
    img = _openrouter_generate_image(article) if ENABLE_IMAGES else ""
    if ENABLE_IMAGES and not img:
        img = _pollinations_fallback_image(article)

    sent = False
    try:
        if img:
            res = _send_photo_with_button(caption, img, url)
            sent = bool(res and res.get("ok"))
        if not sent:
            _tg_api(
                "sendMessage",
                {
                    "chat_id": _normalize_channel(TELEGRAM_CHANNEL),
                    "text": caption,
                    "parse_mode": "HTML",
                    "reply_markup": {
                        "inline_keyboard": [[{"text": "Читать полностью", "url": url}]]
                    },
                    "disable_web_page_preview": False,
                },
            )
            sent = True
    except Exception as e:
        print("TG ERROR:", e)
        sent = False

    if sent:
        _mark_sent(key)
    return sent


def publish_manual_post(title: str, text: str, url: str = ""):
    if not _is_configured():
        raise RuntimeError("Telegram env is not configured")
    base = f"<b>{title.strip()}</b>\n\n{text.strip()}\n\n<i>{STYLE}</i>"
    markup = None
    if url:
        markup = {"inline_keyboard": [[{"text": "Читать полностью", "url": url.strip()}]]}
    payload = {
        "chat_id": _normalize_channel(TELEGRAM_CHANNEL),
        "text": base,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    if markup:
        payload["reply_markup"] = markup
    return _tg_api("sendMessage", payload)

