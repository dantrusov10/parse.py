import base64
import difflib
import hashlib
import json
import os
import re
import time
import html as html_lib
import urllib.parse
import urllib.error
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
IMG_MODEL = os.getenv("IMG_MODEL", "google/gemini-2.5-flash-image").strip()
IMG_FALLBACK_MODELS = [x.strip() for x in os.getenv("IMG_FALLBACK_MODELS", "").split(",") if x.strip()]
IMG_SIZE = os.getenv("IMG_SIZE", "1536x1024").strip()
IMG_STRICT_OPENROUTER = os.getenv("IMG_STRICT_OPENROUTER", "0").strip().lower() in ("1", "true", "yes")
AI_COMMENT_ENABLED = os.getenv("TG_AI_COMMENT_ENABLED", "1").strip().lower() not in ("0", "false", "no")
AI_COMMENT_MODEL = os.getenv("TG_AI_COMMENT_MODEL", "openai/gpt-4o-mini").strip()
AI_COMMENT_MAX_CHARS = int(os.getenv("TG_AI_COMMENT_MAX_CHARS", "520"))
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip() or IMG_API_KEY

SENT_STORE = os.getenv("TELEGRAM_SENT_STORE", "/var/tmp/newlevel_tg_sent.json")
DAILY_STORE = os.getenv("TELEGRAM_DAILY_STORE", "/var/tmp/newlevel_tg_daily.json")
SIMILAR_STORE = os.getenv("TELEGRAM_SIMILAR_STORE", "/var/tmp/newlevel_tg_similar.json")
SIMILARITY_THRESHOLD = float(os.getenv("TG_SIMILARITY_THRESHOLD", "0.86"))
WHITELIST_RAW = os.getenv(
    "TG_SOURCE_WHITELIST",
    "habr.com,vc.ru,cnews,comnews,ведомости,it world,ria,lenta,newlevel"
).strip().lower()
WHITELIST = [x.strip() for x in WHITELIST_RAW.split(",") if x.strip()]

_TRANSLATION_PREFIX_RE = re.compile(
    r"^\s*\[\s*Перевод\s*\]\s*[:\-–—\.]?\s*",
    re.IGNORECASE,
)


def _strip_translation_prefix(text: str) -> str:
    if not text:
        return text
    t = text.strip()
    t = _TRANSLATION_PREFIX_RE.sub("", t, count=1)
    return t.strip()


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


def _shorten_plain(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip(" ,.;:") + "…"


def _normalize_commentary(text: str) -> str:
    text = (text or "").strip()
    parts = [re.sub(r"[ \t]+", " ", p).strip() for p in text.split("\n\n")]
    parts = [p for p in parts if p]
    text = "\n\n".join(parts)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _build_caption(article: dict, for_photo: bool = False) -> str:
    """vc.ru-style: заголовок + тема + только редакционный комментарий + ссылка (без анонса статьи)."""
    title = _strip_translation_prefix((article.get("title") or "Без заголовка").strip())
    src = (article.get("src") or "Источник").strip()
    cat = (article.get("cat") or "IT-продажи").strip()
    commentary = _normalize_commentary(
        _strip_translation_prefix(_ai_editor_comment(article) or _editor_comment(article))
    )
    read_more_url = (article.get("url") or "").strip()

    title_e = html_lib.escape(title)
    src_e = html_lib.escape(src)
    cat_e = html_lib.escape(cat)
    commentary_e = html_lib.escape(commentary)
    read_more_url_e = html_lib.escape(read_more_url)

    def _compose(curr_title: str, curr_commentary: str, url_e: str, url_raw: str) -> str:
        link = f'<a href="{url_raw}">{url_e}</a>' if url_raw else url_e
        return (
            f"<b>{curr_title}</b>\n\n"
            f"<i>{cat_e} · {src_e}</i>\n\n"
            f"{curr_commentary}\n\n"
            f"{link}"
        )

    caption = _compose(title_e, commentary_e, read_more_url_e, read_more_url)
    if for_photo:
        max_caption_len = 980
        title_photo = html_lib.escape(_shorten_plain(title, 200))
        if len(caption) > max_caption_len:
            commentary_short = html_lib.escape(_shorten_plain(commentary, 320))
            caption = _compose(title_photo, commentary_short, read_more_url_e, read_more_url)
        if len(caption) > max_caption_len:
            commentary_short = html_lib.escape(_shorten_plain(commentary, 220))
            caption = _compose(title_photo, commentary_short, read_more_url_e, read_more_url)
        if len(caption) > max_caption_len:
            short_url = _shorten_plain(read_more_url, 96)
            short_url_e = html_lib.escape(short_url)
            caption = (
                f"<b>{title_photo}</b>\n\n"
                f"<i>{cat_e}</i>\n\n"
                f"{commentary_short}\n\n"
                f'<a href="{read_more_url}">{short_url_e}</a>'
            )
    return caption


def _editor_comment(article: dict) -> str:
    cat = (article.get("cat") or "").strip()
    title = (article.get("title") or "").strip().lower()
    if cat == "ИИ":
        return "Нейросети в продажах — не про «магию», а про дисциплину данных. Если заголовок цепляет, читайте, где автор честно проходит по граблям."
    if cat == "Маркетинг":
        return "Тут либо про деньги и воронку, либо про красивые картинки. Ставьте на первое — остальное приложится."
    if cat == "Тендеры":
        return "Госзакупки любят сюрпризы в сроках и формулировках. Загляните в текст, если готовите КП на этой неделе."
    if "crm" in title or "продаж" in title:
        return "CRM-темы быстро превращаются в религию. Ищите в материале один практический рычаг под ваш пайплайн."
    return "Короткий материал — проверьте, есть ли здесь угол, который можно забрать в планёрку без двухчасового разбора."


def _ai_editor_comment(article: dict) -> str:
    if not AI_COMMENT_ENABLED or not OPENROUTER_API_KEY:
        return ""
    title = (article.get("title") or "").strip()
    cat = (article.get("cat") or "IT-продажи").strip()
    src = (article.get("src") or "Источник").strip()
    if not title:
        return ""

    system = (
        "Ты редактор Telegram-канала NewLevel CRM в духе vc.ru: плотно, по-человечески, с фокусом на IT/B2B-продажи, маркетинг, ИИ и тендеры. "
        "Пишешь короткий редакционный комментарий от команды (не дайджест и не пересказ). "
        "Запрещено: повторять или перефразировать текст новости/анонса, «вода», общие фразы вроде «важно отметить», списки, хэштеги, обращение «дорогие друзья». "
        "Разрешено: 1–2 абзаца через пустую строку, конкретная мысль, лёгкая ирония если уместна теме, редкий короткий вопрос к читателю. "
        "Стиль: цепляет, хочется открыть ссылку. Только русский язык. "
        f"Лимит: не больше {AI_COMMENT_MAX_CHARS} символов (включая пробелы и переносы)."
    )
    user = (
        f"Категория ленты: {cat}\n"
        f"Источник материала: {src}\n"
        f"Заголовок (единственный опорный факт — не цитируй его дословно целиком): {title}\n\n"
        "Напиши только текст комментария для Telegram-подписи. Не добавляй ссылку и не дублируй заголовок."
    )
    payload = {
        "model": AI_COMMENT_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.72,
        "max_tokens": 280,
    }
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "HTTP-Referer": "https://nwlvl.ru",
            "X-Title": "NewLevel CRM News Bot",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=35) as resp:
            raw = resp.read().decode("utf-8")
        data = json.loads(raw or "{}")
        content = (
            (data.get("choices") or [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
        content = re.sub(r"\s+", " ", content).strip(" -\n\t")
        content = _strip_translation_prefix(content)
        if not content:
            return ""
        if len(content) > AI_COMMENT_MAX_CHARS:
            content = content[:AI_COMMENT_MAX_CHARS].rstrip(" ,.;:") + "…"
        return content
    except Exception as e:
        print("AI COMMENT WARN:", e)
        return ""


def _image_prompt(article: dict) -> str:
    title = _strip_translation_prefix((article.get("title") or "").strip())
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
            # OpenRouter image generation works via chat completions + image modality.
            url = "https://openrouter.ai/api/v1/chat/completions"
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "modalities": ["image", "text"],
            }
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {IMG_API_KEY}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "HTTP-Referer": "https://nwlvl.ru",
                    "X-Title": "NewLevel CRM News Bot",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=80) as resp:
                raw = resp.read().decode("utf-8", "ignore")
            data = json.loads(raw or "{}")
            msg = ((data.get("choices") or [{}])[0].get("message") or {})
            images = msg.get("images") or []
            if not images:
                continue
            image_url = ((images[0].get("image_url") or {}).get("url") or "").strip()
            # Most image-capable models return data URL (base64 PNG).
            if image_url.startswith("data:image") and ";base64," in image_url:
                b64 = image_url.split(";base64,", 1)[1]
                img_bytes = base64.b64decode(b64)
                file_name = f"/var/tmp/newlevel_tg_img_{int(time.time())}.png"
                with open(file_name, "wb") as f:
                    f.write(img_bytes)
                return file_name
            if image_url.startswith("http://") or image_url.startswith("https://"):
                return image_url
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "ignore")
            # Known non-recoverable cases for this model; try next fallback model silently.
            if (
                "not a valid model id" in body.lower()
                or "no endpoints found" in body.lower()
                or "unsupported_country_region_territory" in body.lower()
            ):
                continue
            print(f"IMG WARN ({model}): HTTP {e.code} {body[:220]}")
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


def _send_photo(caption: str, image_url_or_path: str):
    # Telegram Bot API sendPhoto in multipart mode for bytes is harder in stdlib;
    # use URL mode first, fallback to text post if unsupported.
    if image_url_or_path.startswith("http://") or image_url_or_path.startswith("https://"):
        if TG_RELAY_URL and TG_RELAY_SECRET:
            payload = {
                "chat_id": _normalize_channel(TELEGRAM_CHANNEL),
                "image_url": image_url_or_path,
                "caption": caption,
                "parse_mode": "HTML",
            }
            return _tg_api("sendPhotoByUrl", payload)
        payload = {
            "chat_id": _normalize_channel(TELEGRAM_CHANNEL),
            "photo": image_url_or_path,
            "caption": caption,
            "parse_mode": "HTML",
        }
        return _tg_api("sendPhoto", payload)
    if TG_RELAY_URL and TG_RELAY_SECRET and os.path.exists(image_url_or_path):
        with open(image_url_or_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        payload = {
            "chat_id": _normalize_channel(TELEGRAM_CHANNEL),
            "image_base64": b64,
            "caption": caption,
            "parse_mode": "HTML",
        }
        return _tg_api("sendPhotoBase64", payload)
    return None


def _normalize_text(text: str) -> str:
    text = html_lib.unescape(text or "").lower().replace("\xa0", " ")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[^a-zа-я0-9\s]", " ", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


def _source_allowed(article: dict) -> bool:
    src = (article.get("src") or "").lower()
    url = (article.get("url") or "").lower()
    if not WHITELIST:
        return True
    hay = f"{src} {url}"
    return any(w in hay for w in WHITELIST)


def _too_similar(article: dict) -> bool:
    title = _normalize_text(article.get("title") or "")
    excerpt = _normalize_text(article.get("excerpt") or "")
    curr = f"{title} {excerpt}".strip()
    if not curr:
        return False
    cur_hash = hashlib.sha1(curr.encode("utf-8")).hexdigest()
    store = _load_json(SIMILAR_STORE, {"items": []})
    items = list(store.get("items", []))
    for old in items:
        old_text = old.get("text", "")
        if not old_text:
            continue
        ratio = difflib.SequenceMatcher(None, curr, old_text).ratio()
        if ratio >= SIMILARITY_THRESHOLD:
            print(f"TG SKIP: similar post detected (ratio={ratio:.2f})")
            return True
    items.append({"hash": cur_hash, "text": curr, "ts": int(time.time())})
    store["items"] = items[-500:]
    _save_json(SIMILAR_STORE, store)
    return False


def publish_article(article: dict, relevance_score: int = 0):
    if not _is_configured():
        return False
    if relevance_score < MIN_SCORE:
        print(f"TG SKIP: score {relevance_score} < {MIN_SCORE}")
        return False
    if not _source_allowed(article):
        print("TG SKIP: source is not in whitelist")
        return False
    if _too_similar(article):
        return False
    url = (article.get("url") or "").strip()
    if not url:
        return False
    key = url
    if _already_sent(key):
        return False
    if not _daily_guard_ok():
        return False

    caption = _build_caption(article, for_photo=False)
    photo_caption = _build_caption(article, for_photo=True)
    img = _openrouter_generate_image(article) if ENABLE_IMAGES else ""
    if ENABLE_IMAGES and not img and not IMG_STRICT_OPENROUTER:
        img = _pollinations_fallback_image(article)

    sent = False
    try:
        if img:
            try:
                res = _send_photo(photo_caption, img)
                sent = bool(res and res.get("ok"))
            except Exception as e:
                print("TG PHOTO WARN:", e)
                sent = False
        if not sent:
            _tg_api(
                "sendMessage",
                {
                    "chat_id": _normalize_channel(TELEGRAM_CHANNEL),
                    "text": caption,
                    "parse_mode": "HTML",
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
    if url:
        base += f"\n\nЧитать полностью: {url.strip()}"
    payload = {
        "chat_id": _normalize_channel(TELEGRAM_CHANNEL),
        "text": base,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    return _tg_api("sendMessage", payload)

