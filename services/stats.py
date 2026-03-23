"""
Statistics and chart-related logic.

Responsibilities:
- Profit calculation
- Bad trade detection
- Recommendation generation
- Dashboard aggregate stats
- Chart data shaping
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any


def calculate_profit(trade: dict[str, Any]) -> float:
    """
    Calculate profit for a trade.

    Current project rule:
    - Prefer avg_price when present
    - Otherwise fall back to price

    Formula:
    profit = seeds_received - (comparison_price * quantity)
    """
    comparison_price = trade.get("avg_price") or trade.get("price", 0)
    quantity = trade.get("quantity", 0)
    seeds = trade.get("seeds", 0)

    return float(seeds) - (float(comparison_price) * int(quantity))


def detect_bad_trade(trade: dict[str, Any]) -> bool:
    """
    Mark a trade as 'bad' when seeds received are below 50% of expected value.

    Expected value:
    avg_price * quantity
    """
    avg_price = float(trade.get("avg_price", 0))
    quantity = int(trade.get("quantity", 0))
    seeds = float(trade.get("seeds", 0))

    if avg_price <= 0 or quantity <= 0:
        return False

    expected_value = avg_price * quantity
    return seeds < (expected_value * 0.5)


def should_sell(item: dict[str, Any] | None) -> str:
    """
    Very simple recommendation logic based on item value.

    This stays close to your current project behavior.
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

    Important fix:
    'most_traded' counts total quantity traded, not just number of entries.
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
        quantity = int(trade.get("quantity", 1))
        seeds = int(trade.get("seeds", 0))
        profit = float(trade.get("profit", 0))
        is_bad_trade = bool(trade.get("bad_trade", False))

        total_seeds += seeds
        total_profit += profit
        item_quantities[item_name] += quantity

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

    Included charts:
    - profit_over_time:
      cumulative profit line

    - item_breakdown:
      total traded quantity by item
    """
    # -------------------------------------------------------------------------
    # Profit-over-time data:
    # Sort by timestamp ascending so the chart moves forward in time.
    # -------------------------------------------------------------------------
    trades_in_time_order = sorted(trades, key=lambda t: t.get("timestamp", ""))

    cumulative_profit = 0.0
    profit_labels: list[str] = []
    profit_values: list[float] = []

    for index, trade in enumerate(trades_in_time_order, start=1):
        cumulative_profit += float(trade.get("profit", 0))
        label = trade.get("timestamp", "")[:10] or f"Trade {index}"
        profit_labels.append(label)
        profit_values.append(round(cumulative_profit, 2))

    # -------------------------------------------------------------------------
    # Item breakdown chart:
    # Sum total quantity per item.
    # -------------------------------------------------------------------------
    quantity_by_item: dict[str, int] = defaultdict(int)
    for trade in trades:
        item_name = trade.get("item", "Unknown")
        quantity = int(trade.get("quantity", 1))
        quantity_by_item[item_name] += quantity

    # Sort descending so the biggest categories appear first.
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