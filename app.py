"""
Main Flask application for the Arc Raiders Trade Tracker.

What this version improves:
- Moves business logic into dedicated service modules
- Adds server-side pagination, sorting, and filtering
- Adds edit and delete routes
- Adds lightweight autocomplete API
- Avoids import-time API calls by lazy-loading the item cache
- Keeps the routes much thinner and easier to maintain

Important design note:
This version still uses JSON storage to stay close to your current project.
That means it is still simple to run locally, but the code is structured so
moving to SQLite later will be much easier.
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
    save_trades,
    update_trade_by_id,
)

import uuid

app = Flask(__name__)


@app.route("/")
def index():
    """
    Dashboard route.

    Server-side responsibilities:
    - Reads query parameters for filtering, sorting, and pagination
    - Filters the full list of trades on the server
    - Sorts the filtered list on the server
    - Slices only the requested page for rendering
    - Builds chart data from the filtered dataset
    """
    all_trades = load_trades()

    # -------------------------------------------------------------------------
    # Read query parameters.
    # These drive the server-side dashboard behavior.
    # -------------------------------------------------------------------------
    search_query = (request.args.get("q") or "").strip().lower()
    sort_by = (request.args.get("sort") or "newest").strip().lower()
    bad_only = (request.args.get("bad_only") or "").strip().lower() in {"1", "true", "yes", "on"}
    min_profit = request.args.get("min_profit", "").strip()
    max_profit = request.args.get("max_profit", "").strip()
    page = request.args.get("page", "1").strip()

    # -------------------------------------------------------------------------
    # Parse numeric inputs carefully.
    # Invalid values fall back to "no filter" instead of crashing.
    # -------------------------------------------------------------------------
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

    # -------------------------------------------------------------------------
    # Filter trades on the server.
    # This replaces the fragile client-side filtering logic from the old page.
    # -------------------------------------------------------------------------
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

    # -------------------------------------------------------------------------
    # Sort trades on the server.
    # This is far more reliable than sorting DOM elements in JavaScript.
    # -------------------------------------------------------------------------
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
        # ---------------------------------------------------------------------
        # "newest" default:
        # Sort by timestamp descending.
        # ---------------------------------------------------------------------
        filtered_trades.sort(key=lambda t: t.get("timestamp", ""), reverse=True)
        sort_by = "newest"

    # -------------------------------------------------------------------------
    # Pagination.
    # Only send the current page to the template.
    # -------------------------------------------------------------------------
    per_page = 10
    total_items = len(filtered_trades)
    total_pages = max(1, ceil(total_items / per_page))

    if current_page > total_pages:
        current_page = total_pages

    start_index = (current_page - 1) * per_page
    end_index = start_index + per_page
    page_trades = filtered_trades[start_index:end_index]

    # -------------------------------------------------------------------------
    # Stats + charts are built from the FILTERED dataset because that usually
    # feels better in dashboards: what you see matches the summary.
    # -------------------------------------------------------------------------
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


@app.route("/add", methods=["GET", "POST"])
def add_trade():
    """
    Add a new trade.

    GET:
    - Render the form

    POST:
    - Validate inputs
    - Enrich with item metadata if available
    - Save to JSON storage
    """
    if request.method == "POST":
        item_name = (request.form.get("item") or "").strip()
        quantity_raw = (request.form.get("quantity") or "").strip()
        price_raw = (request.form.get("price") or "").strip()
        avg_price_raw = (request.form.get("avg_price") or "").strip()
        seeds_raw = (request.form.get("seeds") or "").strip()

        if not item_name:
            return "Item name is required.", 400

        try:
            quantity = int(quantity_raw)
            price = float(price_raw)
            avg_price = float(avg_price_raw)
            seeds = int(seeds_raw)
        except ValueError:
            return "Quantity, price, avg price, and seeds must be valid numbers.", 400

        if quantity <= 0:
            return "Quantity must be greater than 0.", 400

        item_data = find_item(item_name)

        add_trade_record(
            item=item_name,
            quantity=quantity,
            price=price,
            avg_price=avg_price,
            seeds=seeds,
            timestamp=datetime.now().isoformat(),
            item_data=item_data,
        )

        return redirect(url_for("index"))

    return render_template("add_trade.html")


@app.route("/edit/<trade_id>", methods=["GET", "POST"])
def edit_trade(trade_id: str):
    """
    Edit an existing trade by its unique id.
    """
    trade = get_trade_by_id(trade_id)
    if trade is None:
        return "Trade not found.", 404

    if request.method == "POST":
        item_name = (request.form.get("item") or "").strip()
        quantity_raw = (request.form.get("quantity") or "").strip()
        price_raw = (request.form.get("price") or "").strip()
        avg_price_raw = (request.form.get("avg_price") or "").strip()
        seeds_raw = (request.form.get("seeds") or "").strip()

        if not item_name:
            return "Item name is required.", 400

        try:
            quantity = int(quantity_raw)
            price = float(price_raw)
            avg_price = float(avg_price_raw)
            seeds = int(seeds_raw)
        except ValueError:
            return "Quantity, price, avg price, and seeds must be valid numbers.", 400

        if quantity <= 0:
            return "Quantity must be greater than 0.", 400

        item_data = find_item(item_name)

        update_trade_by_id(
            trade_id=trade_id,
            item=item_name,
            quantity=quantity,
            price=price,
            avg_price=avg_price,
            seeds=seeds,
            item_data=item_data,
        )

        return redirect(url_for("index"))

    return render_template("edit_trade.html", trade=trade)


@app.post("/delete/<trade_id>")
def delete_trade(trade_id: str):
    """
    Delete a trade by id, then redirect back to dashboard.
    """
    deleted = delete_trade_by_id(trade_id)
    if not deleted:
        return "Trade not found.", 404

    return redirect(url_for("index"))


@app.route("/api/items")
def api_items():
    """
    Lightweight autocomplete endpoint.

    This replaces the old pattern where every item was dumped directly into the
    HTML template as a giant JSON object.
    """
    query = (request.args.get("q") or "").strip()
    matches = search_item_names(query, limit=10)
    return jsonify(matches)


if __name__ == "__main__":
    app.run(debug=True)