"""
Item caching + lookup logic.

This version includes:
- in-memory cache
- disk cache
- stale fallback if API fails
- fast O(1) lookup for find_item
"""

from __future__ import annotations

import json
import os
import time
import requests

API_URL = "https://metaforge.app/api/arc-raiders/items"
CACHE_FILE = "items_cache.json"
CACHE_TTL_SECONDS = 6 * 60 * 60  # 6 hours

# -----------------------------------------------------------------------------
# Global caches
# -----------------------------------------------------------------------------
_ITEM_CACHE = None           # full list
_ITEM_LOOKUP = {}            # name -> item dict


# -----------------------------------------------------------------------------
# Safe file write (prevents corruption)
# -----------------------------------------------------------------------------
def _atomic_write_json(path, data):
    temp_path = path + ".tmp"

    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())

    os.replace(temp_path, path)


# -----------------------------------------------------------------------------
# Fetch from API (paginated)
# -----------------------------------------------------------------------------
def _fetch_items_from_api():
    all_items = []
    page = 1
    limit = 100

    while True:
        url = f"{API_URL}?page={page}&limit={limit}"

        try:
            response = requests.get(url, timeout=(3, 10))
            response.raise_for_status()
        except requests.exceptions.RequestException:
            break

        data = response.json()
        items = data.get("data", [])

        if not items:
            break

        all_items.extend(items)

        if not data.get("pagination", {}).get("hasNextPage", False):
            break

        page += 1

    return all_items


# -----------------------------------------------------------------------------
# MAIN CACHE FUNCTION (THIS IS THE IMPORTANT ONE)
# -----------------------------------------------------------------------------
def get_item_cache():
    global _ITEM_CACHE, _ITEM_LOOKUP

    # -------------------------------------------------------------------------
    # 1. Return in-memory cache if already loaded
    # -------------------------------------------------------------------------
    if _ITEM_CACHE is not None:
        return _ITEM_CACHE

    disk_cache = None

    # -------------------------------------------------------------------------
    # 2. Try reading disk cache (even if stale)
    # -------------------------------------------------------------------------
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                disk_cache = json.load(f)
        except:
            disk_cache = None

    # -------------------------------------------------------------------------
    # 3. If cache exists AND is fresh → use it
    # -------------------------------------------------------------------------
    if disk_cache:
        age = time.time() - os.path.getmtime(CACHE_FILE)

        if age < CACHE_TTL_SECONDS:
            _ITEM_CACHE = disk_cache

            # Build fast lookup table
            _ITEM_LOOKUP = {
                (item.get("name") or "").lower(): item
                for item in _ITEM_CACHE
            }

            return _ITEM_CACHE

    # -------------------------------------------------------------------------
    # 4. Try fetching fresh data from API
    # -------------------------------------------------------------------------
    api_items = _fetch_items_from_api()

    if api_items:
        _ITEM_CACHE = api_items

        # Save to disk
        _atomic_write_json(CACHE_FILE, api_items)

        # Build lookup
        _ITEM_LOOKUP = {
            (item.get("name") or "").lower(): item
            for item in _ITEM_CACHE
        }

        return _ITEM_CACHE

    # -------------------------------------------------------------------------
    # 5. 🔥 FALLBACK: use stale cache if API failed
    # -------------------------------------------------------------------------
    if disk_cache:
        _ITEM_CACHE = disk_cache

        _ITEM_LOOKUP = {
            (item.get("name") or "").lower(): item
            for item in _ITEM_CACHE
        }

        return _ITEM_CACHE

    # -------------------------------------------------------------------------
    # 6. Last resort: empty list
    # -------------------------------------------------------------------------
    _ITEM_CACHE = []
    _ITEM_LOOKUP = {}
    return _ITEM_CACHE


# -----------------------------------------------------------------------------
# FAST ITEM LOOKUP (O(1))
# -----------------------------------------------------------------------------
def find_item(name: str):
    """
    Find an item instantly using cached lookup.

    This avoids scanning the full list every time.
    """

    if not name:
        return None

    # Ensure cache is loaded
    if _ITEM_CACHE is None:
        get_item_cache()

    normalized_name = name.strip().lower()

    return _ITEM_LOOKUP.get(normalized_name)