"""Optional external enrichment providers.  They are called only on explicit actions."""

from __future__ import annotations

import hashlib
import mimetypes
from pathlib import Path
from typing import Any

import requests

from database import DATA_DIR

RAWG_BASE_URL = "https://api.rawg.io/api"
COVERS_DIR = DATA_DIR / "covers"


class ProviderError(RuntimeError):
    pass


def search_rawg(title: str, api_key: str) -> list[dict[str, Any]]:
    if not api_key.strip():
        raise ProviderError("Configure a RAWG API key first.")
    response = requests.get(
        f"{RAWG_BASE_URL}/games",
        params={"key": api_key.strip(), "search": title, "search_precise": "true", "page_size": 5},
        timeout=20,
    )
    if response.status_code == 401:
        raise ProviderError("RAWG rejected the configured API key.")
    if response.status_code == 429:
        raise ProviderError("RAWG reached rate limit. Please try again later.")
    try:
        response.raise_for_status()
    except requests.RequestException as exc:
        raise ProviderError(f"Failed to search RAWG: {exc}") from exc
    return response.json().get("results", [])


def get_rawg_game(slug_or_id: str | int, api_key: str) -> dict[str, Any]:
    response = requests.get(
        f"{RAWG_BASE_URL}/games/{slug_or_id}",
        params={"key": api_key.strip()},
        timeout=20,
    )
    try:
        response.raise_for_status()
    except requests.RequestException as exc:
        raise ProviderError(f"Failed to fetch RAWG details: {exc}") from exc
    return response.json()


def fetch_rawg_metadata(title: str, api_key: str) -> tuple[dict[str, Any] | None, str | None]:
    """Return the best RAWG detail record and a human-readable match note."""
    results = search_rawg(title, api_key)
    if not results:
        return None, "RAWG no devolvió coincidencias."
    best = results[0]
    try:
        detail = get_rawg_game(best["slug"], api_key)
    except KeyError:
        return None, "RAWG devolvió una coincidencia sin identificador válido."
    return detail, f"Coincidencia automática: {detail.get('name', title)}"


def cache_cover(image_url: str | None, game_id: int) -> str | None:
    """Download a cover once to the local cache and return its relative path."""
    if not image_url:
        return None
    COVERS_DIR.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(image_url.encode("utf-8")).hexdigest()[:12]
    response = requests.get(image_url, timeout=30)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "").split(";")[0]
    extension = mimetypes.guess_extension(content_type) or ".jpg"
    filename = f"{game_id}_{digest}{extension}"
    destination = COVERS_DIR / filename
    destination.write_bytes(response.content)
    return str(destination.relative_to(DATA_DIR.parent))
