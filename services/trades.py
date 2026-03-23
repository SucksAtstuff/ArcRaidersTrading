import sqlite3
import uuid
from typing import Any

from services.stats import calculate_profit, detect_bad_trade, should_sell

DB_FILE = "trades.db"


# -----------------------------------------------------------------------------
# DB CONNECTION
# -----------------------------------------------------------------------------
def get_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row  # return dict-like rows
    return conn


# -----------------------------------------------------------------------------
# INIT DATABASE (AUTO CREATE TABLE)
# -----------------------------------------------------------------------------
def init_db():
    """
    Initialize database and create indexes for fast queries.

    Indexes dramatically improve:
    - sorting (timestamp, seeds, profit)
    - filtering (item searches)
    """

    conn = get_connection()
    cursor = conn.cursor()

    # -------------------------------------------------------------------------
    # TABLE
    # -------------------------------------------------------------------------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS trades (
        id TEXT PRIMARY KEY,
        item TEXT,
        quantity INTEGER,
        price REAL,
        avg_price REAL,
        seeds INTEGER,
        timestamp TEXT,
        rarity TEXT,
        value REAL,
        recommendation TEXT,
        bad_trade INTEGER,
        profit REAL
    )
    """)

    # -------------------------------------------------------------------------
    # 🔥 INDEXES (THIS IS THE BIG WIN)
    # -------------------------------------------------------------------------

    # Fast sorting by time
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON trades(timestamp DESC)")

    # Fast sorting/filtering by seeds
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_seeds ON trades(seeds)")

    # Fast sorting/filtering by profit
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_profit ON trades(profit)")

    # Fast search by item name
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_item ON trades(item)")

    conn.commit()
    conn.close()


# -----------------------------------------------------------------------------
# BUILD TRADE RECORD (UNCHANGED LOGIC)
# -----------------------------------------------------------------------------
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
):
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

    trade["bad_trade"] = int(detect_bad_trade(trade))
    trade["profit"] = calculate_profit(trade)

    return trade


# -----------------------------------------------------------------------------
# LOAD ALL TRADES
# -----------------------------------------------------------------------------
def load_trades():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM trades")
    rows = cursor.fetchall()

    conn.close()

    return [dict(row) for row in rows]


# -----------------------------------------------------------------------------
# ADD TRADE
# -----------------------------------------------------------------------------
def add_trade_record(
    *,
    item: str,
    quantity: int,
    price: float,
    avg_price: float,
    seeds: int,
    timestamp: str,
    item_data: dict[str, Any] | None,
):
    conn = get_connection()
    cursor = conn.cursor()

    trade = _build_trade_record(
        item=item,
        quantity=quantity,
        price=price,
        avg_price=avg_price,
        seeds=seeds,
        timestamp=timestamp,
        item_data=item_data,
    )

    cursor.execute("""
        INSERT INTO trades VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        trade["id"],
        trade["item"],
        trade["quantity"],
        trade["price"],
        trade["avg_price"],
        trade["seeds"],
        trade["timestamp"],
        trade["rarity"],
        trade["value"],
        trade["recommendation"],
        trade["bad_trade"],
        trade["profit"],
    ))

    conn.commit()
    conn.close()

    return trade


# -----------------------------------------------------------------------------
# GET TRADE
# -----------------------------------------------------------------------------
def get_trade_by_id(trade_id: str):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM trades WHERE id = ?", (trade_id,))
    row = cursor.fetchone()

    conn.close()

    return dict(row) if row else None


# -----------------------------------------------------------------------------
# UPDATE TRADE
# -----------------------------------------------------------------------------
def update_trade_by_id(
    *,
    trade_id: str,
    item: str,
    quantity: int,
    price: float,
    avg_price: float,
    seeds: int,
    item_data: dict[str, Any] | None,
):
    conn = get_connection()
    cursor = conn.cursor()

    trade = _build_trade_record(
        trade_id=trade_id,
        item=item,
        quantity=quantity,
        price=price,
        avg_price=avg_price,
        seeds=seeds,
        timestamp="",  # keep old timestamp if needed later
        item_data=item_data,
    )

    cursor.execute("""
        UPDATE trades SET
            item = ?,
            quantity = ?,
            price = ?,
            avg_price = ?,
            seeds = ?,
            rarity = ?,
            value = ?,
            recommendation = ?,
            bad_trade = ?,
            profit = ?
        WHERE id = ?
    """, (
        trade["item"],
        trade["quantity"],
        trade["price"],
        trade["avg_price"],
        trade["seeds"],
        trade["rarity"],
        trade["value"],
        trade["recommendation"],
        trade["bad_trade"],
        trade["profit"],
        trade_id
    ))

    conn.commit()
    conn.close()

    return trade


# -----------------------------------------------------------------------------
# DELETE
# -----------------------------------------------------------------------------
def delete_trade_by_id(trade_id: str):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM trades WHERE id = ?", (trade_id,))
    conn.commit()

    deleted = cursor.rowcount > 0

    conn.close()
    return deleted