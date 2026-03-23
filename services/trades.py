"""
Trade storage and mutation logic.

Responsibilities:
- Load and save trades from JSON
- Add trade records
- Update trade records
- Delete trade records
- Lookup trades by unique id

This module keeps persistence concerns away from route handlers.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any

from services.stats import calculate_profit, detect_bad_trade, should_sell

TRADES_FILE = "trades.json"


def _atomic_write_json(path: str, data: Any) -> None:
    """
    Safely write JSON to disk using a temporary file and atomic replace.
    """
    temp_path = f"{path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as file_handle:
        json.dump(data, file_handle, indent=4)
        file_handle.flush()
        os.fsync(file_handle.fileno())

    os.replace(temp_path, path)


def load_trades() -> list[dict[str, Any]]:
    """
    Load trades from disk.

    Returns:
    - empty list if file is missing
    - empty list if file is invalid JSON
    """
    if not os.path.exists(TRADES_FILE):
        return []

    try:
        with open(TRADES_FILE, "r", encoding="utf-8") as file_handle:
            data = json.load(file_handle)
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def save_trades(trades: list[dict[str, Any]]) -> None:
    """
    Persist all trades safely.
    """
    _atomic_write_json(TRADES_FILE, trades)


def _build_trade_record(
    *,
    item: str,
    quantity: int,
    price: float,
    avg_price: float,
    seeds: int,
    timestamp: str,
    item_data: dict[str, Any] | None,
    trade_id: str | None = None,
) -> dict[str, Any]:
    """
    Build one normalized trade record.

    This centralizes how trade objects are created so add/edit behavior stays
    consistent.
    """
    trade = {
        "id": trade_id or uuid.uuid4().hex,
        "item": item,
        "quantity": quantity,
        "price": price,
        "avg_price": avg_price,
        "seeds": seeds,
        "timestamp": timestamp,
        "rarity": item_data.get("rarity") if item_data else None,
        "value": item_data.get("value") if item_data else None,
        "recommendation": should_sell(item_data),
    }

    trade["bad_trade"] = detect_bad_trade(trade)
    trade["profit"] = calculate_profit(trade)

    return trade


def add_trade_record(
    *,
    item: str,
    quantity: int,
    price: float,
    avg_price: float,
    seeds: int,
    timestamp: str,
    item_data: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Add a new trade to storage and return it.
    """
    trades = load_trades()

    trade = _build_trade_record(
        item=item,
        quantity=quantity,
        price=price,
        avg_price=avg_price,
        seeds=seeds,
        timestamp=timestamp,
        item_data=item_data,
    )

    trades.append(trade)
    save_trades(trades)
    return trade


def get_trade_by_id(trade_id: str) -> dict[str, Any] | None:
    """
    Return one trade by id, or None if missing.
    """
    for trade in load_trades():
        if trade.get("id") == trade_id:
            return trade
    return None


def update_trade_by_id(
    *,
    trade_id: str,
    item: str,
    quantity: int,
    price: float,
    avg_price: float,
    seeds: int,
    item_data: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """
    Update an existing trade by id.

    Returns:
    - updated trade if found
    - None if missing
    """
    trades = load_trades()

    for index, existing_trade in enumerate(trades):
        if existing_trade.get("id") != trade_id:
            continue

        updated_trade = _build_trade_record(
            trade_id=trade_id,
            item=item,
            quantity=quantity,
            price=price,
            avg_price=avg_price,
            seeds=seeds,
            timestamp=existing_trade.get("timestamp", ""),
            item_data=item_data,
        )

        trades[index] = updated_trade
        save_trades(trades)
        return updated_trade

    return None


def delete_trade_by_id(trade_id: str) -> bool:
    """
    Delete a trade by id.

    Returns:
    - True if deleted
    - False if no trade matched
    """
    trades = load_trades()
    original_count = len(trades)

    remaining_trades = [trade for trade in trades if trade.get("id") != trade_id]
    if len(remaining_trades) == original_count:
        return False

    save_trades(remaining_trades)
    return True