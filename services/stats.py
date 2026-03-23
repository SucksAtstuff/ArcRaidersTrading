"""
Statistics and chart-related logic.

UPDATED FOR BUY/SELL SUPPORT:
- Handles negative quantities (SELL trades)
- Uses absolute values where needed
- Prevents incorrect "most traded" results
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any


def calculate_profit(trade: dict[str, Any]) -> float:
    """
    Calculate profit for a trade.

    UPDATED:
    Uses absolute quantity so BUY/SELL both work.

    BUY:
        seeds is negative → profit becomes positive if bought cheap

    SELL:
        seeds is positive → profit is normal
    """
    comparison_price = trade.get("avg_price") or trade.get("price", 0)

    # 🔥 IMPORTANT FIX
    quantity = abs(int(trade.get("quantity", 0)))

    seeds = float(trade.get("seeds", 0))

    return float(seeds) - (float(comparison_price) * quantity)


def detect_bad_trade(trade: dict[str, Any]) -> bool:
    """
    Only applies to SELL trades.

    A trade is bad if:
    seeds received < 50% of expected value
    """

    quantity = int(trade.get("quantity", 0))

    # 🔥 Only SELL trades (negative quantity)
    if quantity >= 0:
        return False

    avg_price = float(trade.get("avg_price", 0))
    seeds = float(trade.get("seeds", 0))

    if avg_price <= 0:
        return False

    expected_value = avg_price * abs(quantity)
    return seeds < (expected_value * 0.5)


def should_sell(item: dict[str, Any] | None) -> str:
    """
    Very simple recommendation logic based on item value.
    """
    if not item:
        return "Unknown"

    value = item.get("value", 0)

    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        numeric_value = 0

    if numeric_value > 1000:
        return "SELL"
    if numeric_value > 500:
        return "MAYBE"
    return "HOLD"


def calculate_stats(trades: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Build dashboard summary stats.

    FIXES:
    - Uses absolute quantity for most traded
    - Works with buy/sell system
    """

    if not trades:
        return {
            "total_seeds": 0,
            "total_profit": 0,
            "most_traded": "N/A",
            "bad_trade_count": 0,
            "trade_count": 0,
        }

    total_seeds = 0
    total_profit = 0.0
    item_quantities: dict[str, int] = defaultdict(int)
    bad_trade_count = 0

    for trade in trades:
        item_name = trade.get("item", "Unknown")
        quantity = int(trade.get("quantity", 0))
        seeds = int(trade.get("seeds", 0))
        profit = float(trade.get("profit", 0))
        is_bad_trade = bool(trade.get("bad_trade", False))

        total_seeds += seeds
        total_profit += profit

        # 🔥 FIX: use absolute quantity
        item_quantities[item_name] += abs(quantity)

        if is_bad_trade:
            bad_trade_count += 1

    most_traded = max(item_quantities, key=item_quantities.get) if item_quantities else "N/A"

    return {
        "total_seeds": total_seeds,
        "total_profit": total_profit,
        "most_traded": most_traded,
        "bad_trade_count": bad_trade_count,
        "trade_count": len(trades),
    }


def build_chart_data(trades: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Build chart payloads for the dashboard.

    FIX:
    - Uses absolute quantities
    """

    trades_in_time_order = sorted(trades, key=lambda t: t.get("timestamp", ""))

    cumulative_profit = 0.0
    profit_labels: list[str] = []
    profit_values: list[float] = []

    for index, trade in enumerate(trades_in_time_order, start=1):
        cumulative_profit += float(trade.get("profit", 0))
        label = trade.get("timestamp", "")[:10] or f"Trade {index}"
        profit_labels.append(label)
        profit_values.append(round(cumulative_profit, 2))

    quantity_by_item: dict[str, int] = defaultdict(int)

    for trade in trades:
        item_name = trade.get("item", "Unknown")
        quantity = int(trade.get("quantity", 0))

        quantity_by_item[item_name] += abs(quantity)

    sorted_item_quantities = sorted(
        quantity_by_item.items(),
        key=lambda pair: pair[1],
        reverse=True,
    )

    item_labels = [item_name for item_name, _ in sorted_item_quantities]
    item_values = [quantity for _, quantity in sorted_item_quantities]

    return {
        "profit_over_time": {
            "labels": profit_labels,
            "values": profit_values,
        },
        "item_breakdown": {
            "labels": item_labels,
            "values": item_values,
        },
    }