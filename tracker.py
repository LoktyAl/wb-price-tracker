import requests
import json
import os

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
DROP_THRESHOLD = 0.25
PRICES_FILE = "prices.json"


def get_wb_price(nm_id: int):
      url = f"https://card.wb.ru/cards/v1/detail?appType=1&curr=rub&dest=-1257786&nm={nm_id}"
      try:
                resp = requests.get(url, timeout=10)
                products = resp.json().get("data", {}).get("products", [])
                if not products:
                              return None
                          p = products[0]
                return {
                    "price": p.get("salePriceU", 0) / 100,
                    "name": p.get("name", "")
                }
except Exception as e:
        print(f"Ошибка {nm_id}: {e}")
        return None


def send_telegram(message: str):
      url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
      requests.post(url, data={
          "chat_id": TELEGRAM_CHAT_ID,
          "text": message,
          "parse_mode": "HTML"
      })


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
                            print(f"Не удалось получить данные для {item['nmId']}")
                            continue

              current_price = data["price"]
              name = data["name"] or item["name"]
              print(f"{name}: {current_price} руб.")

        if nm_id in saved:
                      old_price = saved[nm_id]
                      if old_price > 0:
                                        drop = (old_price - current_price) / old_price
                                        if drop >= DROP_THRESHOLD:
                                                              link = f"https://www.wildberries.ru/catalog/{item['nmId']}/detail.aspx"
                                                              msg = (
                                                                  f"🔥 <b>Цена упала на {drop*100:.1f}%!</b>\n\n"
                                                                  f"📦 {name}\n"
                                                                  f"💰 Было: {old_price:.0f} руб.\n"
                                                                  f"✅ Стало: <b>{current_price:.0f} руб.</b>\n"
                                                                  f"🔗 <a href='{link}'>Открыть на WB</a>"
                                                              )
                                                              send_telegram(msg)
                                                              print(f"  → Уведомление отправлено! -{drop*100:.1f}%")
                                                              saved[nm_id] = current_price
                      else:
                                            print(f"  → Изменение: {(old_price-current_price):+.0f} руб. ({drop*100:.1f}%)")
        else:
            saved[nm_id] = current_price
                      print(f"  → Добавлен в отслеживание")

    save_prices(saved)
    print("Готово.")


if __name__ == "__main__":
      main()
