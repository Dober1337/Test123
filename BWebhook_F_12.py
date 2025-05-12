import os
import time
import hashlib
import hmac
import requests
from dotenv import load_dotenv
from urllib.parse import urlencode
from flask import Flask, request, jsonify

# .env-Variablen laden
load_dotenv()

# API Keys aus Umgebungsvariablen
api_key = os.getenv("BINANCE_API_KEY")
api_secret = os.getenv("BINANCE_API_SECRET")

app = Flask(__name__)

# Konfiguration
usdt_per_order = 80.0
max_open_positions = 2  # Maximal 2 Long-Positionen (entspricht pyramiding=2)
open_positions = 0      # Long-Position-Zähler

# Binance Futures URL (Hedge Mode aktiv)
BASE_URL = "https://fapi.binance.com"

# Preis abrufen
def get_symbol_price(symbol):
    res = requests.get(f"{BASE_URL}/fapi/v1/ticker/price", params={"symbol": symbol})
    return float(res.json()["price"])

# Menge anhand USDT berechnen
def calculate_quantity(price):
    qty = usdt_per_order / price
    return round(qty, 3)

# Order platzieren
def place_futures_order(symbol, side, position_side, quantity):
    timestamp = int(time.time() * 1000)
    params = {
        "symbol": symbol,
        "side": side.upper(),  # BUY oder SELL
        "positionSide": position_side,  # LONG oder SHORT
        "type": "MARKET",
        "quantity": quantity,
        "timestamp": timestamp,
        "recvWindow": 5000
    }
    query = urlencode(params)
    signature = hmac.new(api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
    url = f"{BASE_URL}/fapi/v1/order?{query}&signature={signature}"
    headers = {"X-MBX-APIKEY": api_key}
    res = requests.post(url, headers=headers)
    if res.status_code == 200:
        print(f"✅ {side.upper()} {position_side} erfolgreich:", res.json())
        return True
    else:
        print(f"❌ Fehler bei Order: {res.text}")
        return False

# Webhook-Endpunkt
@app.route('/webhook', methods=['POST'])
def webhook():
    global open_positions

    data = request.get_json()
    print("Raw:", data)

    if not data or "action" not in data or "symbol" not in data:
        return jsonify({"status": "error", "message": "Fehlende Daten"}), 400

    action = data["action"].lower()
    symbol = data["symbol"].upper()

    # Kurs prüfen
    price = get_symbol_price(symbol)
    if price <= 0:
        return jsonify({"status": "error", "message": "Ungültiger Preis"}), 400

    quantity = calculate_quantity(price)
    if quantity <= 0:
        return jsonify({"status": "error", "message": "Menge zu gering"}), 400

    if action == "buy":
        if open_positions >= max_open_positions:
            print("⚠️ Max. LONG-Positionen aktiv")
            return jsonify({"status": "ignored", "message": "Max erreicht"}), 200

        if place_futures_order(symbol, "BUY", "LONG", quantity):
            open_positions += 1
            print(f"📈 Neue LONG – Gesamt: {open_positions}")
            return jsonify({"status": "success"}), 200
        else:
            return jsonify({"status": "error", "message": "Buy fehlgeschlagen"}), 500

    elif action == "close_long":
        if open_positions > 0:
            open_positions -= 1
            print(f"🔁 LONG geschlossen – übrig: {open_positions}")
            return jsonify({"status": "closed"}), 200
        else:
            print("ℹ️ Keine Long-Position aktiv")
            return jsonify({"status": "none_active"}), 200

    elif action == "close_short":
        print("⚠️ Short-Position ignoriert (nicht verwendet)")
        return jsonify({"status": "ignored", "message": "Short deaktiviert"}), 200

    return jsonify({"status": "unknown_action"}), 400

# Serverstart
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002)
