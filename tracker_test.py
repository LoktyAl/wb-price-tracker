import requests
import json
import os
import time
import random
import sys
from urllib.parse import quote

def log(*a):
    print(*a, flush=True)

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
PRODUCTS_FILE = "products.json"

STOP_WORDS = [
    "\u043d\u0430\u0431\u043e\u0440", "\u043a\u043e\u043c\u043f\u043b\u0435\u043a\u0442", "\u0447\u0435\u0445\u043e\u043b", "\u0444\u043e\u0442\u043e\u0433\u0440\u0430\u0444", "\u0441\u0442\u0435\u043a\u043b\u043e",
    "\u0430\u043a\u0441\u0435\u0441\u0441\u0443\u0430\u0440", "\u0437\u0430\u0449\u0438\u0442", "\u043f\u043b\u0451\u043d\u043a", "\u043f\u043b\u0435\u043d\u043a", "\u0431\u0430\u043c\u043f\u0435\u0440",
    "\u0437\u0430\u0440\u044f\u0434", "\u043a\u0430\u0431\u0435\u043b", "\u0434\u043b\u044f \u0441\u043c\u0430\u0440\u0442\u0444\u043e\u043d", "\u043a \u0441\u043c\u0430\u0440\u0442\u0444\u043e\u043d",
]

CN_MARKERS = [
    "chinese version", "china version", "\u043a\u0438\u0442\u0430\u0439\u0441\u043a\u0430\u044f \u0432\u0435\u0440\u0441", "\u043a\u0438\u0442\u0430\u0439\u0441\u043a\u0430\u044f \u043f\u0440\u043e\u0448\u0438\u0432",
    "global rom", "\u0433\u043b\u043e\u0431\u0430\u043b \u0440\u043e\u043c", " cn ", " cn,", "(cn)", " ct ", "(ct)", " ct,",
    " china", "china)", "\u043a\u0438\u0442\u0430\u0439 \u0432\u0435\u0440\u0441",
]

HEADERS_WB = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    "Origin": "https://www.wildberries.ru",
    "Referer": "https://www.wildberries.ru/",
    "x-requested-with": "XMLHttpRequest",
}

HEADERS_OZON = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "ru-RU,ru;q=0.9",
}

WB_SEARCH_HOSTS = [
    "https://search.wb.ru/exactmatch/ru/common/v5/search",
    "https://search.wb.ru/exactmatch/ru/common/v4/search",
    "https://u-search.wb.ru/exactmatch/ru/common/v5/search",
]
WB_DESTS = ["-1257786", "-1255987"]
MAX_RETRIES = 3

OZON_TIMEOUT = 8
OZON_MAX_PRODUCTS = 3
OZON = {"enabled": True, "fails": 0}


def is_chinese_version(name):
    low = " " + name.lower() + " "
    return any(m in low for m in CN_MARKERS)

def is_junk(name):
    low = name.lower()
    return any(w in low for w in STOP_WORDS)

def memory_ok(name, want_gb):
    if not want_gb:
        return True
    low = name.lower().replace(" ", "")
    if want_gb == 512:
        return "512" in low and "1024" not in low
    if want_gb == 256:
        return "256" in low
    return str(want_gb) in low

def passes_filters(name, model):
    low = name.lower()
    if is_junk(name):
        return False
    if is_chinese_version(name):
        return False
    for inc in model.get("must_include", []):
        if inc.lower() not in low:
            return False
    for exc in model.get("must_exclude", []):
        if exc.lower() in low:
            return False
    if not memory_ok(name, model.get("memory", 0)):
        return False
    return True

def est_duty(price_rub, cfg):
    threshold = cfg.get("duty_free_eur", 200) * cfg.get("eur_rate", 105)
    if price_rub <= threshold:
        return 0
    return round((price_rub - threshold) * cfg.get("duty_rate", 0.15))

# ----------------------------- Wildberries -----------------------------

def wb_search(query):
    session = requests.Session()
    for host in WB_SEARCH_HOSTS:
        for dest in WB_DESTS:
            url = (host + "?appType=1&curr=rub&dest=" + dest +
                   "&spp=30&resultset=catalog&sort=popular&page=1&query=" + quote(query))
            for retry in range(MAX_RETRIES):
                try:
                    r = session.get(url, timeout=15, headers=HEADERS_WB)
                    log("WB '" + query + "' status " + str(r.status_code))
                    if r.status_code == 429:
                        time.sleep((2 ** retry) + random.uniform(0, 1.0))
                        continue
                    if r.status_code != 200 or not r.text.strip():
                        break
                    data = r.json()
                    prods = data.get("data", {}).get("products", []) or data.get("products", [])
                    if prods:
                        return prods
                    break
                except Exception as e:
                    log("  WB err: " + str(e))
                    time.sleep(1 + retry)
    return []

def wb_price(p):
    for size in p.get("sizes", []):
        sp = size.get("price") or {}
        if sp.get("product"):
            return sp["product"] / 100
    if p.get("salePriceU"):
        return p["salePriceU"] / 100
    if p.get("priceU"):
        return p["priceU"] / 100
    return None

def wb_is_foreign(p, name):
    low = name.lower()
    if "\u043d\u0430\u0445\u043e\u0434\u043a" in low or "\u0438\u0437 \u043a\u0438\u0442\u0430\u044f" in low or "aliexpress" in low:
        return True
    if p.get("dtype") == 4:
        return True
    return False

def wb_scan(model, cfg):
    out = []
    disc = cfg.get("wb_card_discount", 0.06)
    for p in wb_search(model["query"])[:15]:
        name = p.get("name", "")
        if not passes_filters(name, model):
            continue
        base = wb_price(p)
        if base is None or base < model.get("min_price", 0):
            continue
        card = round(base * (1 - disc))
        foreign = wb_is_foreign(p, name)
        duty = est_duty(card, cfg) if foreign else 0
        out.append({
            "market": "WB", "name": name,
            "url": "https://www.wildberries.ru/catalog/" + str(p.get("id")) + "/detail.aspx",
            "base": base, "card": card, "duty": duty,
            "duty_est": foreign, "total": card + duty,
        })
    return out


# ----------------------------- Ozon -----------------------------

def ozon_get(path):
    """Single GET to Ozon composer API with short timeout and kill-switch."""
    if not OZON["enabled"]:
        return None
    url = "https://www.ozon.ru/api/composer-api.bx/page/json/v2?url=" + quote(path, safe="")
    try:
        r = requests.get(url, timeout=OZON_TIMEOUT, headers=HEADERS_OZON)
        if r.status_code != 200:
            OZON["fails"] += 1
            log("  OZON status " + str(r.status_code) + " fails=" + str(OZON["fails"]))
        else:
            OZON["fails"] = 0
            return r.json()
    except Exception as e:
        OZON["fails"] += 1
        log("  OZON err: " + str(e)[:60] + " fails=" + str(OZON["fails"]))
    if OZON["fails"] >= 3:
        OZON["enabled"] = False
        log("  OZON disabled after repeated failures (blocked from CI)")
    return None

def ozon_search_ids(query):
    data = ozon_get("/search/?text=" + query)
    if not data:
        return []
    ws = data.get("widgetStates", {})
    ids = []
    for k, v in ws.items():
        if not k.startswith("tileGrid"):
            continue
        try:
            tile = json.loads(v)
        except Exception:
            continue
        for item in tile.get("items", []):
            link = ""
            act = item.get("action")
            if isinstance(act, dict):
                link = act.get("link", "")
            if not link:
                link = item.get("link", "") or ""
            for part in link.replace("?", "/").split("/"):
                if part.isdigit() and len(part) >= 7:
                    ids.append(part)
    seen = set(); res = []
    for i in ids:
        if i not in seen:
            seen.add(i); res.append(i)
    return res[:OZON_MAX_PRODUCTS]

def ozon_product(pid):
    data = ozon_get("/product/" + pid + "/")
    if not data:
        return None
    ws = data.get("widgetStates", {})
    name = ""; card = None; duty = 0
    for k, v in ws.items():
        if k.startswith("webProductHeading"):
            try:
                name = json.loads(v).get("title", "")
            except Exception:
                pass
    for k, v in ws.items():
        if k.startswith("webPrice"):
            try:
                pj = json.loads(v)
                cp = pj.get("cardPrice") or pj.get("price") or ""
                digits = "".join(ch for ch in cp if ch.isdigit())
                if digits:
                    card = int(digits)
            except Exception:
                pass
    for k, v in ws.items():
        if k.startswith("webIconWithText") and "\u043f\u043e\u0448\u043b\u0438\u043d" in v:
            try:
                obj = json.loads(v)
                txt = " ".join(t.get("content", "") for t in obj.get("textRs", []))
                digits = "".join(ch for ch in txt if ch.isdigit())
                if digits:
                    duty = int(digits)
            except Exception:
                pass
    return {"name": name, "card": card, "duty": duty}

def ozon_scan(model, cfg):
    out = []
    if not OZON["enabled"]:
        return out
    for pid in ozon_search_ids(model["query"]):
        if not OZON["enabled"]:
            break
        info = ozon_product(pid)
        if not info or info.get("card") is None:
            continue
        name = info["name"]
        if not passes_filters(name, model):
            continue
        if info["card"] < model.get("min_price", 0):
            continue
        out.append({
            "market": "Ozon", "name": name,
            "url": "https://www.ozon.ru/product/" + pid + "/",
            "base": info["card"], "card": info["card"], "duty": info["duty"],
            "duty_est": False, "total": info["card"] + info["duty"],
        })
        time.sleep(random.uniform(0.3, 0.8))
    return out


# ----------------------------- Telegram + main -----------------------------

def fmt(n):
    return "{:,}".format(int(n)).replace(",", " ")

def send_telegram(message):
    url = "https://api.telegram.org/bot" + TELEGRAM_TOKEN + "/sendMessage"
    try:
        r = requests.post(url, data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }, timeout=15)
        log("TG status " + str(r.status_code))
    except Exception as e:
        log("TG err: " + str(e))

def main():
    with open(PRODUCTS_FILE, encoding="utf-8") as f:
        conf = json.load(f)
    cfg = conf.get("config", {})
    models = conf.get("models", [])

    lines = ["\U0001f9ea <b>\u0422\u0415\u0421\u0422 \u0442\u0440\u0435\u043a\u0435\u0440\u0430</b> \u2014 \u043b\u0443\u0447\u0448\u0438\u0435 \u0446\u0435\u043d\u044b", ""]
    total_found = 0

    for model in models:
        log("=== " + model["label"] + " ===")
        offers = wb_scan(model, cfg)
        offers += ozon_scan(model, cfg)
        total_found += len(offers)
        target = model.get("target", 0)
        lines.append("<b>" + model["label"] + "</b> \u2014 \u0446\u0435\u043b\u044c \u2264 " + fmt(target) + " \u20bd")
        if not offers:
            lines.append("  \u2014 \u043d\u0438\u0447\u0435\u0433\u043e \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u043e")
            lines.append("")
            continue
        offers.sort(key=lambda x: x["total"])
        best = offers[0]
        hit = "\u2705" if best["total"] <= target else "\u274c"
        duty_note = ""
        if best["duty"]:
            sign = "\u2248" if best["duty_est"] else "+"
            duty_note = " (" + fmt(best["card"]) + " " + sign + " \u043f\u043e\u0448\u043b\u0438\u043d\u0430 " + fmt(best["duty"]) + ")"
        lines.append("  " + hit + " " + best["market"] + ": <b>" + fmt(best["total"]) + " \u20bd</b>" + duty_note)
        lines.append("  <a href=\"" + best["url"] + "\">\u041e\u0442\u043a\u0440\u044b\u0442\u044c</a>")
        lines.append("")

    src = "WB + Ozon" if OZON["enabled"] else "\u0442\u043e\u043b\u044c\u043a\u043e WB (Ozon \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u0435\u043d)"
    lines.append("\u0418\u0441\u0442\u043e\u0447\u043d\u0438\u043a\u0438: " + src + ". \u041d\u0430\u0439\u0434\u0435\u043d\u043e: " + str(total_found))
    msg = "\n".join(lines)
    log("Found total: " + str(total_found) + " | ozon_enabled=" + str(OZON["enabled"]))
    if len(msg) > 3900:
        chunk = ""
        for ln in lines:
            if len(chunk) + len(ln) > 3500:
                send_telegram(chunk); chunk = ""
            chunk += ln + "\n"
        if chunk:
            send_telegram(chunk)
    else:
        send_telegram(msg)

if __name__ == "__main__":
    main()
