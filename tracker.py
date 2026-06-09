import requests
import json
import os

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
DROP_THRESHOLD = 0.20
PRICES_FILE = "prices.json"

HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "Origin": "https://www.wildberries.ru",
        "Referer": "https://www.wildberries.ru/",
}

def get_wb_price(nm_id):
        url = f"https://card.wb.ru/cards/v1/detail?appType=1&curr=rub&dest=-1257786&nm={nm_id}"
        try:
                    resp = requests.get(url, timeout=15, headers=HEADERS)
                    print(f"WB API status {nm_id}: {resp.status_code}, len={len(resp.text)}")
                    if resp.status_code != 200 or not resp.text.strip():
                                    print(f"Empty or bad response for {nm_id}")
                                    return None
                                products = resp.json().get("data", {}).get("products", [])
                    if not products:
                                    print(f"No products in response for {nm_id}")
                                    return None
                                p = products[0]
                    return {
                        "price": p.get("salePriceU", 0) / 100,
                        "name": p.get("name", "")
                    }
except Exception as e:
        print(f"Error {nm_id}: {e}")
        return None

def send_telegram(message):
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        try:
                    resp = requests.post(url, data={
                                    "chat_id": TELEGRAM_CHAT_ID,
                                    "text": message,
                                    "parse_mode": "HTML"
                    }, timeout=10)
                    result = resp.json()
                    if result.get("ok"):
                                    print("Telegram: message sent OK")
        else:
                        print(f"Telegram error: {result}")
except Exception as e:
        print(f"Telegram exception: {e}")

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
                print(f"{name}: {current_price} rub")

        if nm_id in saved:
                        old_price = saved[nm_id]
                        if old_price > 0:
                                            drop = (old_price - current_price) / old_price
                                            if drop >= DROP_THRESHOLD:
                                                                    link = f"https://www.wildberries.ru/catalog/{item['nmId']}/detail.aspx"
                                                                    msg = (
                                                                        f"Price dropped {drop*100:.1f}%!\n\n"
                                                                        f"{name}\n"
                                                                        f"Was: {old_price:.0f} rub\n"
                                                                        f"Now: {current_price:.0f} rub\n"
                                                                        f"<a href='{link}'>Open on WB</a>"
                                                                    )
                                                                    send_telegram(msg)
                                                                    print(f"  Notification sent! -{drop*100:.1f}%")
                        else:
                                                print(f"  Change: {(old_price-current_price):+.0f} rub ({drop*100:.1f}%)")
        else:
            print(f"  Added to tracking at {current_price:.0f} rub")

        saved[nm_id] = current_price

    save_prices(saved)
    print("Done.")

if __name__ == "__main__":
        main()
