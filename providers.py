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


from interfaces import UnifiedGameData, MetadataProvider
import database as db

class RAWGProvider(MetadataProvider):
    def __init__(self, api_key: str):
        self.api_key = api_key.strip()
        if not self.api_key:
            raise ProviderError("Configure a RAWG API key first.")

    def get_name(self) -> str:
        return "RAWG"

    def search(self, query: str) -> list[UnifiedGameData]:
        response = requests.get(
            f"{RAWG_BASE_URL}/games",
            params={"key": self.api_key, "search": query, "search_precise": "true", "page_size": 10},
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
        
        results = response.json().get("results", [])
        return [self._map_to_unified(r) for r in results]

    def fetch_details(self, provider_game_id: str) -> tuple[UnifiedGameData, dict[str, Any]]:
        response = requests.get(
            f"{RAWG_BASE_URL}/games/{provider_game_id}",
            params={"key": self.api_key},
            timeout=20,
        )
        try:
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ProviderError(f"Failed to fetch RAWG details: {exc}") from exc
        
        raw_data = response.json()
        return self._map_to_unified(raw_data), raw_data

    def _map_to_unified(self, data: dict[str, Any]) -> UnifiedGameData:
        genres = [g.get("name") for g in data.get("genres", []) if g.get("name")]
        tags = [t.get("name") for t in data.get("tags", []) if t.get("name")]
        devs = [d.get("name") for d in data.get("developers", []) if d.get("name")]
        pubs = [p.get("name") for p in data.get("publishers", []) if p.get("name")]
        age_ratings = []
        if data.get("esrb_rating") and data["esrb_rating"].get("name"):
            age_ratings.append(f"ESRB: {data['esrb_rating']['name']}")
        
        return UnifiedGameData(
            provider_id=str(data.get("id", data.get("slug"))),
            name=data.get("name", ""),
            summary=data.get("description_raw") or data.get("description"),
            first_release_date=data.get("released"),
            cover_url=data.get("background_image"),
            total_rating=data.get("metacritic") or data.get("rating"),
            playtime_hours=data.get("playtime"),
            age_ratings=age_ratings,
            genres=genres,
            themes=tags, # Mapping RAWG tags to themes generally
            developers=devs,
            publishers=pubs
        )


def _get_igdb_token(client_id: str, client_secret: str) -> str:
    token = db.get_setting("igdb_access_token")
    if token:
        return token
    url = f"https://id.twitch.tv/oauth2/token?client_id={client_id}&client_secret={client_secret}&grant_type=client_credentials"
    resp = requests.post(url, timeout=20)
    if not resp.ok:
        raise ProviderError("Could not obtain IGDB token with given credentials.")
    token = resp.json().get("access_token")
    if not token:
        raise ProviderError("Respuesta de token IGDB inválida.")
    db.set_setting("igdb_access_token", token)
    return token

class IGDBProvider(MetadataProvider):
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id.strip()
        self.client_secret = client_secret.strip()
        if not self.client_id or not self.client_secret:
            raise ProviderError("Configure the IGDB Client ID and Secret first.")
        self.token = _get_igdb_token(self.client_id, self.client_secret)
        self.headers = {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json"
        }
        self.base_url = "https://api.igdb.com/v4/games"

    def get_name(self) -> str:
        return "IGDB"

    def search(self, query: str) -> list[UnifiedGameData]:
        q = f'search "{query}"; fields name, slug, cover.url, first_release_date, genres.name, themes.name, involved_companies.company.name, involved_companies.developer, involved_companies.publisher, rating, summary, game_modes.name, multiplayer_modes.*, status; limit 10;'
        response = requests.post(self.base_url, headers=self.headers, data=q, timeout=20)
        try:
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ProviderError(f"Error searching IGDB: {exc}") from exc
        
        results = response.json()
        return [self._map_to_unified(r) for r in results]

    def fetch_details(self, provider_game_id: str) -> tuple[UnifiedGameData, dict[str, Any]]:
        # IGDB IDs are integers but we accept slugs just in case.
        if provider_game_id.isdigit():
            q = f'where id = {provider_game_id}; fields name, slug, cover.url, first_release_date, genres.name, themes.name, involved_companies.company.name, involved_companies.developer, involved_companies.publisher, rating, summary, game_modes.name, multiplayer_modes.*, status; limit 1;'
        else:
            q = f'where slug = "{provider_game_id}"; fields name, slug, cover.url, first_release_date, genres.name, themes.name, involved_companies.company.name, involved_companies.developer, involved_companies.publisher, rating, summary, game_modes.name, multiplayer_modes.*, status; limit 1;'
            
        response = requests.post(self.base_url, headers=self.headers, data=q, timeout=20)
        try:
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ProviderError(f"Error fetching IGDB game details: {exc}") from exc
        
        results = response.json()
        if not results:
            raise ProviderError("Game not found on IGDB.")
        
        raw_data = results[0]
        return self._map_to_unified(raw_data), raw_data

    def _map_to_unified(self, data: dict[str, Any]) -> UnifiedGameData:
        genres = [g.get("name") for g in data.get("genres", []) if g.get("name")]
        themes = [t.get("name") for t in data.get("themes", []) if t.get("name")]
        game_modes = [m.get("name") for m in data.get("game_modes", []) if m.get("name")]
        
        devs = []
        pubs = []
        for inv in data.get("involved_companies", []):
            comp = inv.get("company", {}).get("name")
            if comp:
                if inv.get("developer"): devs.append(comp)
                if inv.get("publisher"): pubs.append(comp)

        cover_url = None
        if "cover" in data and "url" in data["cover"]:
            cover_url = data["cover"]["url"].replace("t_thumb", "t_1080p")
            if not cover_url.startswith("http"):
                cover_url = "https:" + cover_url

        from datetime import datetime
        release_date = None
        if data.get("first_release_date"):
            try:
                release_date = datetime.fromtimestamp(data["first_release_date"]).strftime("%Y-%m-%d")
            except Exception:
                pass

        status_map = {
            0: "Released", 2: "Alpha", 3: "Beta", 4: "Early Access", 5: "Offline", 6: "Cancelled", 7: "Rumored"
        }
        game_status = status_map.get(data.get("status"))

        multiplayer = []
        # Parse boolean subtags
        for mp in data.get("multiplayer_modes", []):
            if mp.get("campaigncoop"): multiplayer.append("Campaign Co-op")
            if mp.get("lancoop"): multiplayer.append("LAN Co-op")
            if mp.get("offlinecoop"): multiplayer.append("Offline Co-op")
            if mp.get("onlinecoop"): multiplayer.append("Online Co-op")
            if mp.get("dropin"): multiplayer.append("Drop-in/Drop-out")

        return UnifiedGameData(
            provider_id=str(data.get("id")),
            name=data.get("name", ""),
            summary=data.get("summary"),
            first_release_date=release_date,
            cover_url=cover_url,
            total_rating=data.get("rating"),
            playtime_hours=None, # IGDB natively doesn't have a reliable playtime field without external IDs
            age_ratings=[], # Needs /age_ratings endpoint for full detail, omitted for brevity as they are ENUMs
            genres=genres,
            themes=themes,
            game_modes=game_modes,
            multiplayer_modes=list(set(multiplayer)),
            game_status=game_status,
            developers=devs,
            publishers=pubs
        )


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
