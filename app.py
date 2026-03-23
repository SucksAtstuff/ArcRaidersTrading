"""
Arc Raiders Trade Tracker
-------------------------
FINAL VERSION:
- Uses manual avg_price (24h) for trade comparison
- No more raider currency comparison
- Safe inputs
- Profit + bad trade detection
"""

from flask import Flask, render_template, request, redirect
import requests
import json
import os
from datetime import datetime

app = Flask(__name__)

API_URL = "https://metaforge.app/api/arc-raiders/items"
TRADES_FILE = "trades.json"
CACHE_FILE = "items_cache.json"


# ==============================
# SAFE PARSING
# ==============================

def safe_int(v, default=0):
    try:
        return int(v)
    except:
        return default


def safe_float(v, default=0.0):
    try:
        return float(v)
    except:
        return default


# ==============================
# DATA STORAGE
# ==============================

def load_trades():
    if not os.path.exists(TRADES_FILE):
        return []

    try:
        with open(TRADES_FILE, "r") as f:
            return json.load(f)
    except:
        return []


def save_trades(trades):
    with open(TRADES_FILE, "w") as f:
        json.dump(trades, f, indent=4)


# ==============================
# FETCH ITEMS (CACHE)
# ==============================

def fetch_items():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            return json.load(f)

    all_items = []
    page = 1
    limit = 100

    while True:
        url = f"{API_URL}?page={page}&limit={limit}"
        res = requests.get(url)

        if res.status_code != 200:
            break

        data = res.json()
        items = data.get("data", [])

        if not items:
            break

        all_items.extend(items)

        if not data.get("pagination", {}).get("hasNextPage"):
            break

        page += 1

    with open(CACHE_FILE, "w") as f:
        json.dump(all_items, f)

    return all_items


ITEM_CACHE = fetch_items()


def find_item(name):
    name = name.lower()
    return next((i for i in ITEM_CACHE if i.get("name","").lower() == name), None)


# ==============================
# LOGIC
# ==============================

def detect_bad_trade(trade):
    avg = trade.get("avg_price", 0)
    if avg <= 0:
        return False

    expected = avg * trade["quantity"]
    return trade["seeds"] < expected * 0.5


def calculate_profit(trade):
    base = trade.get("avg_price") or trade["price"]
    return trade["seeds"] - (base * trade["quantity"])


def should_sell(item):
    if not item:
        return "Unknown"

    value = item.get("value", 0)

    if value > 1000:
        return "SELL"
    elif value > 500:
        return "MAYBE"
    return "HOLD"


def calculate_stats(trades):
    # Dictionary to count how many times each item appears
    item_counts = {}

    for t in trades:
        item = t["item"]

        # Initialize count if item not seen before
        if item not in item_counts:
            item_counts[item] = 0

        # Increment count
        item_counts[item] += t.get("quantity", 1)

    # Find the item with the highest count
    if item_counts:
        most_traded = max(item_counts, key=item_counts.get)
    else:
        most_traded = "N/A"

    return {
        "total_seeds": sum(t["seeds"] for t in trades),
        "total_profit": sum(t.get("profit", 0) for t in trades),
        "most_traded": most_traded
    }


# ==============================
# ROUTES
# ==============================

@app.route("/")
def index():
    trades = load_trades()
    stats = calculate_stats(trades)
    return render_template("index.html", trades=trades, stats=stats)


@app.route("/add", methods=["GET", "POST"])
def add_trade():
    if request.method == "POST":
        item = request.form.get("item")

        quantity = safe_int(request.form.get("quantity"))
        price = safe_float(request.form.get("price"))
        avg_price = safe_float(request.form.get("avg_price"))
        seeds = safe_int(request.form.get("seeds"))

        item_data = find_item(item)

        trade = {
            "item": item,
            "quantity": quantity,
            "price": price,
            "avg_price": avg_price,
            "seeds": seeds,
            "timestamp": datetime.now().isoformat(),
            "rarity": item_data.get("rarity") if item_data else None,
            "value": item_data.get("value") if item_data else None,
            "recommendation": should_sell(item_data)
        }

        trade["bad_trade"] = detect_bad_trade(trade)
        trade["profit"] = calculate_profit(trade)

        trades = load_trades()
        trades.append(trade)
        save_trades(trades)

        return redirect("/")

    return render_template("add_trade.html", items=ITEM_CACHE)


if __name__ == "__main__":
    app.run(debug=True)