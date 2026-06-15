import requests
import json
import os
import time
import random
from datetime import datetime, timezone

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
PRICES_FILE = "prices.json"
PRODUCTS_FILE = "products.json"
CHANGE_THRESHOLD = 0.10  # notify only on >=10% change

SEARCH_HOSTS = [
    "https://search.wb.ru/exactmatch/ru/common/v5/search",
    "https://search.wb.ru/exactmatch/ru/common/v4/search",
    "https://u-search.wb.ru/exactmatch/ru/common/v5/search",
    "https://recom.wb.ru/exactmatch/ru/common/v5/search",
]
DESTS = ["-1257786", "-1255987", "12358062"]
MAX_RETRIES = 4

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Origin": "https://www.wildberries.ru",
    "Referer": "https://www.wildberries.ru/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "cross-site",
    "x-requested-with": "XMLHttpRequest",
}


def extract_price(p):
    """Return product price in rubles from a WB product object, or None."""
    for size in p.get("sizes", []):
        sp = size.get("price") or {}
        if sp.get("product"):
            return sp["product"] / 100
    if p.get("salePriceU"):
        return p["salePriceU"] / 100
    if p.get("priceU"):
        return p["priceU"] / 100
    return None


def fetch_search(query):
    """Try multiple hosts/dests with backoff; return list of products or []."""
    session = requests.Session()
    for host in SEARCH_HOSTS:
        for dest in DESTS:
            url = (
                host + "?appType=1&curr=rub&dest=" + dest +
                "&spp=30&resultset=catalog&sort=popular&page=1&query=" +
                requests.utils.quote(query)
            )
            for retry in range(MAX_RETRIES):
                try:
                    resp = session.get(url, timeout=20, headers=HEADERS)
                    print(f"WB search '{query}' [{host.split('//')[1].split('.')[0]}/dest{dest}]: status {resp.status_code}, len={len(resp.text)}")
                    if resp.status_code == 429:
                        wait = (2 ** retry) + random.uniform(0, 1.5)
                        print(f"  429, backoff {wait:.1f}s")
                        time.sleep(wait)
                        continue
                    if resp.status_code != 200 or not resp.text.strip():
                        break
                    data = resp.json()
                    products = data.get("data", {}).get("products", []) or data.get("products", [])
                    if products:
                        return products
                    break
                except Exception as e:
                    print(f"  error: {e}")
                    time.sleep(1 + retry)
    return []


def scan_query(query, top, min_price, label=""):
    """Scan a WB search query and return list of {nmId, name, price}."""
    products = fetch_search(query)
    results = []
    for p in products[:top]:
        nm_id = p.get("id")
        price = extract_price(p)
        if nm_id is None or price is None:
            continue
        if min_price and price < min_price:
            continue
        raw_name = p.get("name", "")
        name = f"{label} \u2014 {raw_name}" if label else raw_name
        results.append({
            "nmId": nm_id,
            "name": name,
            "price": price,
        })
    return results


def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        resp = requests.post(url, data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }, timeout=10)
        result = resp.json()
        if result.get("ok"):
            print("Telegram: message sent OK")
        else:
            print(f"Telegram error: {result}")
    except Exception as e:
        print(f"Telegram exception: {e}")


def build_message(name, old_price, current_price, link):
    diff = current_price - old_price
    pct = diff / old_price * 100
    sign = "+" if diff > 0 else ""
    arrow = "\U0001f4c9" if diff < 0 else "\U0001f4c8"
    return (
        f"{arrow} <b>{name}</b>\n\n"
        f"\U0001f4b0 \u0411\u044b\u043b\u043e: {old_price:,.0f} \u20bd\n"
        f"\u2705 \u0421\u0442\u0430\u043b\u043e: <b>{current_price:,.0f} \u20bd</b>\n"
        f"\U0001f4ca \u0418\u0437\u043c\u0435\u043d\u0435\u043d\u0438\u0435: {sign}{diff:,.0f} \u20bd ({sign}{pct:.1f}%)\n\n"
        f"<a href=\"{link}\">\U0001f6d2 \u041e\u0442\u043a\u0440\u044b\u0442\u044c \u043d\u0430 Wildberries</a>"
    )


def load_history():
    if os.path.exists(PRICES_FILE):
        with open(PRICES_FILE) as f:
            raw = json.load(f)
        history = {}
        for nm_id, val in raw.items():
            if isinstance(val, list):
                history[nm_id] = val
            else:
                history[nm_id] = [{"date": "migrated", "price": val}]
        return history
    return {}


def save_history(history):
    with open(PRICES_FILE, "w") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def main():
    with open(PRODUCTS_FILE) as f:
        config = json.load(f)

    history = load_history()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    found = {}
    for q in config.get("scan", []):
        items = scan_query(
            q.get("query", ""),
            q.get("top", 5),
            q.get("min_price", 0),
            q.get("label", ""),
        )
        for it in items:
            found[str(it["nmId"])] = it

    print(f"Found {len(found)} products across all queries")

    for nm_id, it in found.items():
        current_price = it["price"]
        name = it["name"]
        link = f"https://www.wildberries.ru/catalog/{nm_id}/detail.aspx"
        series = history.get(nm_id, [])
        last_price = series[-1]["price"] if series else None

        if last_price and last_price > 0:
            change = abs(current_price - last_price) / last_price
            if change >= CHANGE_THRESHOLD:
                send_telegram(build_message(name, last_price, current_price, link))
                print(f"  ALERT {name}: {last_price} -> {current_price} ({change*100:.1f}%)")
            else:
                print(f"  {name}: {current_price:.0f} rub (change {change*100:.1f}%)")
        else:
            print(f"  Added to tracking {name}: {current_price:.0f} rub")

        series.append({"date": now, "price": current_price})
        history[nm_id] = series

    save_history(history)
    print("Done.")


if __name__ == "__main__":
    main()
