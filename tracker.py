import requests
import json
import os

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
PRICES_FILE = "prices.json"
STRONG_DROP_THRESHOLD = 0.20

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Origin": "https://www.wildberries.ru",
    "Referer": "https://www.wildberries.ru/",
}


def get_wb_price(nm_id):
    url = (
        "https://card.wb.ru/cards/v4/detail"
        f"?appType=1&curr=rub&dest=-1257786&spp=30&nm={nm_id}"
    )
    try:
        resp = requests.get(url, timeout=15, headers=HEADERS)
        print(f"WB API status {nm_id}: {resp.status_code}, len={len(resp.text)}")
        if resp.status_code != 200 or not resp.text.strip():
            print(f"Empty or bad response for {nm_id}")
            return None
        data = resp.json()
        products = data.get("products") or data.get("data", {}).get("products", [])
        if not products:
            print(f"No products in response for {nm_id}")
            return None
        p = products[0]
        price = None
        for size in p.get("sizes", []):
            sp = size.get("price") or {}
            if sp.get("product"):
                price = sp["product"] / 100
                break
        if price is None and p.get("salePriceU"):
            price = p["salePriceU"] / 100
        if price is None:
            print(f"No price found for {nm_id}")
            return None
        return {"price": price, "name": p.get("name", "")}
    except Exception as e:
        print(f"Error {nm_id}: {e}")
        return None


def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        resp = requests.post(url, data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
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
    if pct <= -STRONG_DROP_THRESHOLD * 100:
        line = "\u2501" * 12
        return (
            f"\U0001f525\U0001f525\U0001f525 <b>\u0421\u0418\u041b\u042c\u041d\u041e\u0415 \u0421\u041d\u0418\u0416\u0415\u041d\u0418\u0415 \u0426\u0415\u041d\u042b!</b> \U0001f525\U0001f525\U0001f525\n"
            f"{line}\n"
            f"\U0001f4e6 <b>{name}</b>\n\n"
            f"\u274c \u0411\u044b\u043b\u043e: <s>{old_price:,.0f} \u20bd</s>\n"
            f"\U0001f7e2 \u0421\u0442\u0430\u043b\u043e: <b>{current_price:,.0f} \u20bd</b>\n"
            f"\U0001f4b8 \u0412\u042b\u0413\u041e\u0414\u0410: <b>{-diff:,.0f} \u20bd ({pct:.1f}%)</b>\n"
            f"{line}\n"
            f"\u26a1\ufe0f <b>\u0426\u0435\u043d\u0430 \u0443\u043f\u0430\u043b\u0430 \u0431\u043e\u043b\u044c\u0448\u0435 \u0447\u0435\u043c \u043d\u0430 20%!</b>\n\n"
            f"<a href=\"{link}\">\U0001f6d2 \u041e\u0442\u043a\u0440\u044b\u0442\u044c \u043d\u0430 Wildberries</a>"
        )
    arrow = "\U0001f4c9" if diff < 0 else "\U0001f4c8"
    return (
        f"{arrow} <b>{name}</b>\n\n"
        f"\U0001f4b0 \u0411\u044b\u043b\u043e: {old_price:,.0f} \u20bd\n"
        f"\u2705 \u0421\u0442\u0430\u043b\u043e: <b>{current_price:,.0f} \u20bd</b>\n"
        f"\U0001f4ca \u0418\u0437\u043c\u0435\u043d\u0435\u043d\u0438\u0435: {sign}{diff:,.0f} \u20bd ({sign}{pct:.1f}%)\n\n"
        f"<a href=\"{link}\">\U0001f6d2 \u041e\u0442\u043a\u0440\u044b\u0442\u044c \u043d\u0430 Wildberries</a>"
    )


def load_prices():
    if os.path.exists(PRICES_FILE):
        with open(PRICES_FILE) as f:
            return json.load(f)
    return {}


def save_prices(prices):
    with open(PRICES_FILE, "w") as f:
        json.dump(prices, f, ensure_ascii=False, indent=2)


def main():
    with open("products.json") as f:
        products = json.load(f)

    saved = load_prices()

    for item in products:
        nm_id = str(item["nmId"])
        data = get_wb_price(item["nmId"])
        if not data:
            print(f"No data for {item['nmId']}")
            continue

        current_price = data["price"]
        name = data["name"] or item["name"]
        link = f"https://www.wildberries.ru/catalog/{item['nmId']}/detail.aspx"
        print(f"{name}: {current_price} rub")

        if nm_id in saved:
            old_price = saved[nm_id]
            if old_price > 0 and current_price != old_price:
                diff = current_price - old_price
                pct = diff / old_price * 100
                sign = "+" if diff > 0 else ""
                send_telegram(build_message(name, old_price, current_price, link))
                strong = " [STRONG DROP]" if pct <= -STRONG_DROP_THRESHOLD * 100 else ""
                print(f"  Price changed: {old_price} -> {current_price} ({sign}{pct:.1f}%){strong}")
            else:
                print(f"  No change: {current_price:.0f} rub")
        else:
            print(f"  Added to tracking at {current_price:.0f} rub")

        saved[nm_id] = current_price

    save_prices(saved)
    print("Done.")


if __name__ == "__main__":
    main()
