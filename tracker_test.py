"""One-off TEST script: scan configured models and send them to Telegram
with a FAKE price change. Does NOT touch prices.json. Run manually only.
"""
import requests
import json
import os
import time
import random

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
PRODUCTS_FILE = "products.json"
TEST_LIMIT = 40  # max products to send as a test

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
        results.append({"nmId": nm_id, "name": name, "price": price})
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
        f"\U0001f9ea <b>\u0422\u0415\u0421\u0422</b>\n"
        f"{arrow} <b>{name}</b>\n\n"
        f"\U0001f4b0 \u0411\u044b\u043b\u043e: {old_price:,.0f} \u20bd\n"
        f"\u2705 \u0421\u0442\u0430\u043b\u043e: <b>{current_price:,.0f} \u20bd</b>\n"
        f"\U0001f4ca \u0418\u0437\u043c\u0435\u043d\u0435\u043d\u0438\u0435: {sign}{diff:,.0f} \u20bd ({sign}{pct:.1f}%)\n\n"
        f"<a href=\"{link}\">\U0001f6d2 \u041e\u0442\u043a\u0440\u044b\u0442\u044c \u043d\u0430 Wildberries</a>"
    )


def main():
    with open(PRODUCTS_FILE) as f:
        config = json.load(f)

    found = {}
    for q in config.get("scan", []):
        items = scan_query(q.get("query", ""), q.get("top", 5), q.get("min_price", 0), q.get("label", ""))
        for it in items:
            found[str(it["nmId"])] = it

    print(f"Found {len(found)} products; sending up to {TEST_LIMIT} as TEST")

    sent = 0
    for nm_id, it in found.items():
        if sent >= TEST_LIMIT:
            break
        current_price = it["price"]
        name = it["name"]
        link = f"https://www.wildberries.ru/catalog/{nm_id}/detail.aspx"
        old_price = round(current_price * 1.10, 0)
        send_telegram(build_message(name, old_price, current_price, link))
        print(f"  TEST sent {name}: {old_price} -> {current_price}")
        sent += 1
        time.sleep(0.4)

    print("Test done.")


if __name__ == "__main__":
    main()
