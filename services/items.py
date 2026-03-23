"""
Item-related services.

Responsibilities:
- Fetch and cache item metadata from the Metaforge API
- Provide lazy access to the cached item list
- Search item names for autocomplete
- Find a specific item by case-insensitive name match
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import requests

API_URL = "https://metaforge.app/api/arc-raiders/items"
CACHE_FILE = "items_cache.json"
HTTP_TIMEOUT = (3, 10)
CACHE_TTL_SECONDS = 6 * 60 * 60

logger = logging.getLogger(__name__)

_ITEM_CACHE: list[dict[str, Any]] | None = None


def _atomic_write_json(path: str, data: Any) -> None:
    """
    Safely write JSON to disk using a temporary file then atomic replace.

    Why:
    - Prevents partially-written files if the process stops mid-write
    - Reduces risk of corrupt cache files
    """
    temp_path = f"{path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as file_handle:
        json.dump(data, file_handle, indent=2)
        file_handle.flush()
        os.fsync(file_handle.fileno())

    os.replace(temp_path, path)


def _load_cache_from_disk_if_fresh() -> list[dict[str, Any]] | None:
    """
    Return cached items if the cache file exists and is still fresh enough.
    """
    if not os.path.exists(CACHE_FILE):
        return None

    try:
        cache_age_seconds = time.time() - os.path.getmtime(CACHE_FILE)
        if cache_age_seconds > CACHE_TTL_SECONDS:
            return None

        with open(CACHE_FILE, "r", encoding="utf-8") as file_handle:
            data = json.load(file_handle)

        if isinstance(data, list):
            return data

        return None
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to read items cache: %s", exc)
        return None


def _fetch_items_from_api() -> list[dict[str, Any]]:
    """
    Fetch all items from the external API using pagination.

    Notes:
    - Uses request timeout so the app doesn't hang forever
    - Stops gracefully on request failure
    - Returns a list even if partially fetched
    """
    all_items: list[dict[str, Any]] = []
    page = 1
    limit = 100

    while True:
        url = f"{API_URL}?page={page}&limit={limit}"

        try:
            response = requests.get(url, timeout=HTTP_TIMEOUT)
            response.raise_for_status()
        except requests.exceptions.RequestException as exc:
            logger.error("Failed to fetch items from API on page %s: %s", page, exc)
            break

        payload = response.json()
        items = payload.get("data", [])

        if not items:
            break

        all_items.extend(items)

        has_next_page = payload.get("pagination", {}).get("hasNextPage", False)
        if not has_next_page:
            break

        page += 1

    return all_items


def get_item_cache() -> list[dict[str, Any]]:
    """
    Lazy-load the item cache.

    Load order:
    1. In-memory cache if already loaded
    2. Fresh disk cache if available
    3. API fetch, then save to disk
    """
    global _ITEM_CACHE

    if _ITEM_CACHE is not None:
        return _ITEM_CACHE

    disk_cache = _load_cache_from_disk_if_fresh()
    if disk_cache is not None:
        _ITEM_CACHE = disk_cache
        return _ITEM_CACHE

    api_items = _fetch_items_from_api()
    _ITEM_CACHE = api_items

    if api_items:
        try:
            _atomic_write_json(CACHE_FILE, api_items)
        except OSError as exc:
            logger.warning("Failed to write items cache: %s", exc)

    return _ITEM_CACHE


def find_item(name: str) -> dict[str, Any] | None:
    """
    Find one item by exact case-insensitive name.
    """
    if not name:
        return None

    normalized_name = name.strip().lower()
    for item in get_item_cache():
        if (item.get("name") or "").strip().lower() == normalized_name:
            return item

    return None


def search_item_names(query: str, limit: int = 10) -> list[dict[str, str]]:
    """
    Return minimal autocomplete results.

    Each result is intentionally tiny:
    - name only

    That keeps the frontend response small and fast.
    """
    normalized_query = query.strip().lower()
    if not normalized_query:
        return []

    results: list[dict[str, str]] = []
    for item in get_item_cache():
        item_name = (item.get("name") or "").strip()
        if normalized_query in item_name.lower():
            results.append({"name": item_name})

        if len(results) >= limit:
            break

    return results