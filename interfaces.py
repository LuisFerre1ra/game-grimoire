from dataclasses import dataclass, field
from typing import Protocol, Any

@dataclass
class UnifiedGameData:
    provider_id: str
    name: str
    summary: str | None = None
    first_release_date: str | None = None
    cover_url: str | None = None
    total_rating: float | None = None
    playtime_hours: float | None = None
    age_ratings: list[str] = field(default_factory=list)
    genres: list[str] = field(default_factory=list)
    themes: list[str] = field(default_factory=list)
    game_modes: list[str] = field(default_factory=list)
    multiplayer_modes: list[str] = field(default_factory=list)
    game_status: str | None = None
    developers: list[str] = field(default_factory=list)
    publishers: list[str] = field(default_factory=list)

class MetadataProvider(Protocol):
    def get_name(self) -> str:
        """Return the name of the provider (e.g. 'RAWG', 'IGDB')."""
        ...

    def search(self, query: str) -> list[UnifiedGameData]:
        """Search for games by title and return unified metadata."""
        ...

    def fetch_details(self, provider_game_id: str) -> tuple[UnifiedGameData, dict[str, Any]]:
        """Fetch detailed info for a game. Returns (UnifiedData, RawJSONResponse)."""
        ...
