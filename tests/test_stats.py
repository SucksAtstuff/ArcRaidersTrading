"""
Minimal test coverage for the most important core logic.

Focus:
- profit calculation
- most traded logic

Why these first:
- They are pure logic
- They are fast to run
- They directly protect bugs you already ran into
"""

from services.stats import calculate_profit, calculate_stats


def test_calculate_profit_prefers_avg_price_when_present():
    """
    If avg_price exists and is truthy, the app uses it as the comparison price.
    """
    trade = {
        "quantity": 2,
        "price": 3.0,
        "avg_price": 10.0,
        "seeds": 30,
    }

    result = calculate_profit(trade)

    assert result == 10.0


def test_calculate_profit_falls_back_to_price_when_avg_price_missing():
    """
    If avg_price is missing/falsy, profit should use price instead.
    """
    trade = {
        "quantity": 4,
        "price": 5.0,
        "avg_price": 0.0,
        "seeds": 30,
    }

    result = calculate_profit(trade)

    assert result == 10.0


def test_calculate_stats_most_traded_uses_total_quantity_not_entry_count():
    """
    This protects the exact dashboard bug you mentioned earlier.

    'Osprey Blueprint' appears across two trades totaling quantity 3.
    'Seeker Grenade Blueprint' appears once with quantity 1.

    The correct most_traded result is Osprey Blueprint.
    """
    trades = [
        {
            "item": "Osprey Blueprint",
            "quantity": 2,
            "seeds": 40,
            "profit": 10,
            "bad_trade": False,
        },
        {
            "item": "Seeker Grenade Blueprint",
            "quantity": 1,
            "seeds": 10,
            "profit": 1,
            "bad_trade": False,
        },
        {
            "item": "Osprey Blueprint",
            "quantity": 1,
            "seeds": 20,
            "profit": 2,
            "bad_trade": False,
        },
    ]

    stats = calculate_stats(trades)

    assert stats["most_traded"] == "Osprey Blueprint"


def test_calculate_stats_handles_empty_list():
    """
    Empty input should not crash and should return sane defaults.
    """
    stats = calculate_stats([])

    assert stats["total_seeds"] == 0
    assert stats["total_profit"] == 0
    assert stats["most_traded"] == "N/A"
    assert stats["bad_trade_count"] == 0
    assert stats["trade_count"] == 0