"""
Main Flask application for the Arc Raiders Trade Tracker.

Fixes included:
- Debug logging for add/edit issues
- Safer error handling
- Removed unused uuid import (belongs in services layer)

Buy/sell enhancement added:
- Add trade form now supports trade_type
- BUY  => +item quantity, -seeds
- SELL => -item quantity, +seeds
"""

from __future__ import annotations

from datetime import datetime
from math import ceil

from flask import Flask, jsonify, redirect, render_template, request, url_for

from services.items import find_item, search_item_names
from services.stats import build_chart_data, calculate_stats
from services.trades import (
    add_trade_record,
    delete_trade_by_id,
    get_trade_by_id,
    load_trades,
    update_trade_by_id,
)

from services.trades import init_db

app = Flask(__name__)
init_db()


# =============================================================================
# DASHBOARD
# =============================================================================
@app.route("/")
def index():
    all_trades = load_trades()

    search_query = (request.args.get("q") or "").strip().lower()
    sort_by = (request.args.get("sort") or "newest").strip().lower()
    bad_only = (request.args.get("bad_only") or "").strip().lower() in {"1", "true", "yes", "on"}
    min_profit = request.args.get("min_profit", "").strip()
    max_profit = request.args.get("max_profit", "").strip()
    page = request.args.get("page", "1").strip()

    # Parse safely
    try:
        min_profit_value = float(min_profit) if min_profit else None
    except ValueError:
        min_profit_value = None

    try:
        max_profit_value = float(max_profit) if max_profit else None
    except ValueError:
        max_profit_value = None

    try:
        current_page = max(1, int(page))
    except ValueError:
        current_page = 1

    # Filtering
    filtered_trades = []
    for trade in all_trades:
        item_name = (trade.get("item") or "").lower()
        profit = float(trade.get("profit", 0))
        is_bad_trade = bool(trade.get("bad_trade", False))

        if search_query and search_query not in item_name:
            continue

        if bad_only and not is_bad_trade:
            continue

        if min_profit_value is not None and profit < min_profit_value:
            continue

        if max_profit_value is not None and profit > max_profit_value:
            continue

        filtered_trades.append(trade)

    # Sorting
    if sort_by == "profit_desc":
        filtered_trades.sort(key=lambda t: float(t.get("profit", 0)), reverse=True)
    elif sort_by == "profit_asc":
        filtered_trades.sort(key=lambda t: float(t.get("profit", 0)))
    elif sort_by == "seeds_desc":
        filtered_trades.sort(key=lambda t: int(t.get("seeds", 0)), reverse=True)
    elif sort_by == "seeds_asc":
        filtered_trades.sort(key=lambda t: int(t.get("seeds", 0)))
    elif sort_by == "item_asc":
        filtered_trades.sort(key=lambda t: (t.get("item") or "").lower())
    elif sort_by == "item_desc":
        filtered_trades.sort(key=lambda t: (t.get("item") or "").lower(), reverse=True)
    else:
        filtered_trades.sort(key=lambda t: t.get("timestamp", ""), reverse=True)
        sort_by = "newest"

    # Pagination
    per_page = 10
    total_items = len(filtered_trades)
    total_pages = max(1, ceil(total_items / per_page))

    if current_page > total_pages:
        current_page = total_pages

    start_index = (current_page - 1) * per_page
    end_index = start_index + per_page
    page_trades = filtered_trades[start_index:end_index]

    stats = calculate_stats(filtered_trades)
    chart_data = build_chart_data(filtered_trades)

    return render_template(
        "index.html",
        trades=page_trades,
        stats=stats,
        chart_data=chart_data,
        current_page=current_page,
        total_pages=total_pages,
        total_items=total_items,
        search_query=search_query,
        sort_by=sort_by,
        bad_only=bad_only,
        min_profit=min_profit,
        max_profit=max_profit,
    )


# =============================================================================
# ADD TRADE
# =============================================================================
@app.route("/add", methods=["GET", "POST"])
def add_trade():
    if request.method == "POST":
        print("DEBUG FORM:", request.form)  # 🔥 DEBUG

        item_name = (request.form.get("item") or "").strip()
        quantity_raw = (request.form.get("quantity") or "").strip()
        price_raw = (request.form.get("price") or "").strip()
        avg_price_raw = (request.form.get("avg_price") or "").strip()
        seeds_raw = (request.form.get("seeds") or "").strip()

        # ---------------------------------------------------------------------
        # NEW:
        # Read the trade type from the form.
        #
        # Expected values:
        # - "buy"
        # - "sell"
        #
        # Defaulting to "sell" preserves safer backwards behavior in case
        # the field is somehow missing.
        # ---------------------------------------------------------------------
        trade_type = (request.form.get("trade_type") or "sell").strip().lower()

        if not item_name:
            return "Item name is required.", 400

        try:
            quantity = int(quantity_raw)
            price = float(price_raw)
            avg_price = float(avg_price_raw)
            seeds = int(seeds_raw)
        except ValueError:
            return "Invalid numbers", 400

        if quantity <= 0:
            return "Quantity must be > 0", 400

        if seeds < 0:
            return "Seeds must be entered as a positive number in the form.", 400

        if trade_type not in {"buy", "sell"}:
            return "Invalid trade type.", 400

        # ---------------------------------------------------------------------
        # CORE BUY/SELL LOGIC
        #
        # We store direction using signs:
        #
        # BUY:
        #   quantity = positive  (you gained the item)
        #   seeds    = negative  (you spent seeds)
        #
        # SELL:
        #   quantity = negative  (you lost the item)
        #   seeds    = positive  (you gained seeds)
        #
        # This keeps your storage model compact and lets the rest of the app
        # continue using one trade record format.
        # ---------------------------------------------------------------------
        if trade_type == "buy":
            quantity = abs(quantity)
            seeds = -abs(seeds)
        else:  # sell
            quantity = -abs(quantity)
            seeds = abs(seeds)

        item_data = find_item(item_name)

        try:
            add_trade_record(
                item=item_name,
                quantity=quantity,
                price=price,
                avg_price=avg_price,
                seeds=seeds,
                timestamp=datetime.now().isoformat(),
                item_data=item_data,
            )
        except Exception as e:
            print("ERROR ADDING TRADE:", e)  # 🔥 DEBUG
            return f"Error saving trade: {e}", 500

        return redirect(url_for("index"))

    return render_template("add_trade.html")


# =============================================================================
# EDIT TRADE
# =============================================================================
@app.route("/edit/<trade_id>", methods=["GET", "POST"])
def edit_trade(trade_id: str):
    trade = get_trade_by_id(trade_id)

    if trade is None:
        print("EDIT FAILED: ID NOT FOUND:", trade_id)  # 🔥 DEBUG
        return "Trade not found.", 404

    if request.method == "POST":
        print("EDIT FORM:", request.form)  # 🔥 DEBUG

        item_name = (request.form.get("item") or "").strip()
        quantity_raw = (request.form.get("quantity") or "").strip()
        price_raw = (request.form.get("price") or "").strip()
        avg_price_raw = (request.form.get("avg_price") or "").strip()
        seeds_raw = (request.form.get("seeds") or "").strip()

        try:
            quantity = int(quantity_raw)
            price = float(price_raw)
            avg_price = float(avg_price_raw)
            seeds = int(seeds_raw)
        except ValueError:
            return "Invalid numbers", 400

        item_data = find_item(item_name)

        try:
            update_trade_by_id(
                trade_id=trade_id,
                item=item_name,
                quantity=quantity,
                price=price,
                avg_price=avg_price,
                seeds=seeds,
                item_data=item_data,
            )
        except Exception as e:
            print("ERROR EDITING:", e)
            return f"Error updating trade: {e}", 500

        return redirect(url_for("index"))

    return render_template("edit_trade.html", trade=trade)


# =============================================================================
# DELETE
# =============================================================================
@app.post("/delete/<trade_id>")
def delete_trade(trade_id: str):
    deleted = delete_trade_by_id(trade_id)

    if not deleted:
        print("DELETE FAILED:", trade_id)  # 🔥 DEBUG
        return "Trade not found.", 404

    return redirect(url_for("index"))


# =============================================================================
# AUTOCOMPLETE API
# =============================================================================
@app.route("/api/items")
def api_items():
    query = (request.args.get("q") or "").strip()
    matches = search_item_names(query, limit=10)
    return jsonify(matches)


# =============================================================================
# RUN
# =============================================================================
if __name__ == "__main__":
    app.run(debug=True)