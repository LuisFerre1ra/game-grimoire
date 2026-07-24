"""Optional external enrichment providers.  They are called only on explicit actions."""

from __future__ import annotations

import hashlib
import mimetypes
import time
from collections import deque
from pathlib import Path
from datetime import datetime, timedelta, UTC
from typing import Any

import requests

from database import DATA_DIR

RAWG_BASE_URL = "https://api.rawg.io/api"
COVERS_DIR = DATA_DIR / "covers"

class ProviderError(RuntimeError):
    pass

from interfaces import UnifiedGameData, MetadataProvider
import database as db

def map_raw_tags(raw_tags: list[str]) -> tuple[dict[str, list[str]], list[str]]:
    mapped = {
        "Genres": [], "Themes": [], "Game modes": [], "Age Rating": [],
        "Status": [], "Reviews": [], "Requirement": [], "Compatibility": [], "Other": []
    }
    unmapped = []
    if not raw_tags:
        return mapped, unmapped
        
    placeholders = ",".join(["?"] * len(raw_tags))
    lower_tags = [r.lower() for r in raw_tags]
    
    with db.connection() as conn:
        rows = conn.execute(
            f"SELECT a.alias_name, t.name, t.category FROM tag_aliases a JOIN tags t ON a.tag_id = t.id WHERE a.alias_name IN ({placeholders})",
            lower_tags
        ).fetchall()
        
    found_aliases = {}
    for r in rows:
        found_aliases[r["alias_name"]] = (r["name"], r["category"])
        
    for raw in raw_tags:
        lower_raw = raw.lower()
        if lower_raw in found_aliases:
            name, cat = found_aliases[lower_raw]
            if cat in mapped and name not in mapped[cat]:
                mapped[cat].append(name)
        else:
            unmapped.append(raw)
            
    return mapped, unmapped

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
        devs = [d.get("name") for d in data.get("developers", []) if d.get("name")]
        pubs = [p.get("name") for p in data.get("publishers", []) if p.get("name")]
        age_ratings = []
        if data.get("esrb_rating") and data["esrb_rating"].get("name"):
            age_ratings.append(f"ESRB: {data['esrb_rating']['name']}")
            
        raw_tags = []
        if data.get("esrb_rating") and data["esrb_rating"].get("name"):
            raw_tags.append(data["esrb_rating"]["name"])
        raw_tags.extend([g.get("name") for g in data.get("genres", []) if g.get("name")])
        raw_tags.extend([t.get("name") for t in data.get("tags", []) if t.get("name")])
        mapped, unmapped = map_raw_tags(raw_tags)
        
        return UnifiedGameData(
            provider_id=str(data.get("id", data.get("slug"))),
            name=data.get("name", ""),
            summary=data.get("description_raw") or data.get("description"),
            first_release_date=data.get("released"),
            cover_url=data.get("background_image"),
            total_rating=data.get("metacritic") or data.get("rating"),
            playtime_hours=data.get("playtime"),
            age_ratings=mapped.get("Age Rating") or age_ratings,
            genres=mapped.get("Genres", []),
            themes=mapped.get("Themes", []),
            game_modes=mapped.get("Game modes", []),
            multiplayer_modes=[],
            developers=devs,
            publishers=pubs
        )

def _clear_igdb_token() -> None:
    """Remove cached IGDB token and its expiry from settings."""
    db.set_setting("igdb_access_token", "")
    db.set_setting("igdb_token_expires_at", "")

def _get_igdb_token(client_id: str, client_secret: str) -> str:
    token = db.get_setting("igdb_access_token")
    expires_at = db.get_setting("igdb_token_expires_at")
    if token and expires_at:
        try:
            if datetime.fromisoformat(expires_at) > datetime.now(tz=UTC):
                return token
        except (ValueError, TypeError):
            pass
        # Token expired or expiry unparseable – clear and re-fetch
        _clear_igdb_token()

    url = f"https://id.twitch.tv/oauth2/token?client_id={client_id}&client_secret={client_secret}&grant_type=client_credentials"
    resp = requests.post(url, timeout=20)
    if not resp.ok:
        raise ProviderError("Could not obtain IGDB token with given credentials.")
    data = resp.json()
    token = data.get("access_token")
    if not token:
        raise ProviderError("Respuesta de token IGDB inválida.")
    expires_in = data.get("expires_in", 0)
    expires_at_dt = datetime.now(tz=UTC) + timedelta(seconds=expires_in)
    db.set_setting("igdb_access_token", token)
    db.set_setting("igdb_token_expires_at", expires_at_dt.isoformat())
    return token

_igdb_request_times = deque(maxlen=4)

def _igdb_post(url: str, headers: dict, data: str, timeout: int = 20):
    max_retries = 3
    for attempt in range(max_retries):
        now = time.time()
        if len(_igdb_request_times) == 4:
            oldest = _igdb_request_times[0]
            elapsed = now - oldest
            if elapsed < 1.1:
                time.sleep(1.1 - elapsed)
        _igdb_request_times.append(time.time())

        response = requests.post(url, headers=headers, data=data, timeout=timeout)
        if response.status_code == 429:
            time.sleep(2)
            continue
        
        response.raise_for_status()
        return response
    
    raise requests.RequestException("IGDB request limit exceeded (429 Too Many Requests).")

class IGDBProvider(MetadataProvider):
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id.strip()
        self.client_secret = client_secret.strip()
        if not self.client_id or not self.client_secret:
            raise ProviderError("Configure the IGDB Client ID and Secret first.")
        self.token = _get_igdb_token(self.client_id, self.client_secret)
        self._build_headers()
        self.base_url = "https://api.igdb.com/v4/games"

    def _build_headers(self) -> None:
        self.headers = {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json"
        }

    def _request(self, url: str, body: str, timeout: int = 20) -> requests.Response:
        """POST to IGDB with retry-on-401 (re-authenticate once)."""
        try:
            response = _igdb_post(url, headers=self.headers, data=body, timeout=timeout)
        except requests.RequestException as exc:
            # Check if the underlying response was a 401
            if hasattr(exc, 'response') and exc.response is not None and exc.response.status_code == 401:
                _clear_igdb_token()
                self.token = _get_igdb_token(self.client_id, self.client_secret)
                self._build_headers()
                response = _igdb_post(url, headers=self.headers, data=body, timeout=timeout)
            else:
                raise
        if response.status_code == 401:
            _clear_igdb_token()
            self.token = _get_igdb_token(self.client_id, self.client_secret)
            self._build_headers()
            response = _igdb_post(url, headers=self.headers, data=body, timeout=timeout)
        return response

    def get_name(self) -> str:
        return "IGDB"

    def search(self, query: str) -> list[UnifiedGameData]:
        q = f'search "{query}"; fields name, slug, cover.url, first_release_date, genres.name, themes.name, involved_companies.company.name, involved_companies.developer, involved_companies.publisher, rating, summary, game_modes.name, multiplayer_modes.*, status; limit 10;'
        try:
            response = self._request(self.base_url, q, timeout=20)
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
            
        try:
            response = self._request(self.base_url, q, timeout=20)
        except requests.RequestException as exc:
            raise ProviderError(f"Error fetching IGDB game details: {exc}") from exc
        
        results = response.json()
        if not results:
            raise ProviderError("Game not found on IGDB.")
        
        raw_data = results[0]
        return self._map_to_unified(raw_data), raw_data

    def _map_to_unified(self, data: dict[str, Any]) -> UnifiedGameData:
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

        release_date = None
        if data.get("first_release_date"):
            try:
                release_date = datetime.fromtimestamp(data["first_release_date"], tz=UTC).strftime("%Y-%m-%d")
            except Exception:
                pass

        status_map = {
            0: "Released", 2: "Alpha", 3: "Beta", 4: "Early Access", 5: "Offline", 6: "Cancelled", 7: "Rumored"
        }
        game_status = status_map.get(data.get("status"))

        raw_tags = []
        raw_tags.extend([g.get("name") for g in data.get("genres", []) if g.get("name")])
        raw_tags.extend([t.get("name") for t in data.get("themes", []) if t.get("name")])
        raw_tags.extend([m.get("name") for m in data.get("game_modes", []) if m.get("name")])
        
        for mp in data.get("multiplayer_modes", []):
            if mp.get("campaigncoop"): raw_tags.append("Campaign Co-op")
            if mp.get("lancoop"): raw_tags.append("LAN Co-op")
            if mp.get("offlinecoop"): raw_tags.append("Offline Co-op")
            if mp.get("onlinecoop"): raw_tags.append("Online Co-op")
        if game_status:
            raw_tags.append(game_status)

        mapped, unmapped = map_raw_tags(raw_tags)

        return UnifiedGameData(
            provider_id=str(data.get("id")),
            name=data.get("name", ""),
            summary=data.get("summary"),
            first_release_date=release_date,
            cover_url=cover_url,
            total_rating=data.get("rating"),
            playtime_hours=None,
            age_ratings=mapped.get("Age Rating", []),
            genres=mapped.get("Genres", []),
            themes=mapped.get("Themes", []),
            game_modes=mapped.get("Game modes", []),
            multiplayer_modes=[],
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