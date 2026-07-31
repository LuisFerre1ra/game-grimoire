"""Unit tests for metadata providers and query escaping."""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add project src/ directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from providers import RAWGProvider, IGDBProvider, ProviderError, map_raw_tags

class TestProviders(unittest.TestCase):
    def test_provider_missing_key_raises_error(self):
        """Test initializing provider with empty key raises ProviderError."""
        with self.assertRaises(ProviderError):
            RAWGProvider(api_key="")

        with self.assertRaises(ProviderError):
            IGDBProvider(client_id="", client_secret="")

    def test_map_raw_tags_empty(self):
        """Test mapping raw tags with empty list."""
        mapped, unmapped = map_raw_tags([])
        self.assertIsInstance(mapped, dict)
        self.assertEqual(unmapped, [])

    @patch("database.get_setting", return_value=None)
    @patch("database.set_setting")
    @patch("requests.post")
    def test_igdb_safe_query_escaping(self, mock_post, mock_set_setting, mock_get_setting):
        """Test that double quotes in IGDB search queries are safely escaped."""
        # Mock token request response
        mock_token_resp = MagicMock()
        mock_token_resp.ok = True
        mock_token_resp.json.return_value = {"access_token": "fake_token", "expires_in": 3600}

        # Mock search query response
        mock_search_resp = MagicMock()
        mock_search_resp.status_code = 200
        mock_search_resp.ok = True
        mock_search_resp.json.return_value = []

        mock_post.side_effect = [mock_token_resp, mock_search_resp]

        provider = IGDBProvider(client_id="test_id", client_secret="test_secret")

        # Search query containing double quotes
        results = provider.search('Super "Mario" Bros')
        self.assertEqual(results, [])

        # Verify second request payload contained escaped quotes 'Super \"Mario\" Bros'
        call_args = mock_post.call_args_list[1]
        posted_data = call_args.kwargs.get("data") or call_args[1].get("data")
        self.assertIn(r'Super \"Mario\" Bros', posted_data)

    def test_igdb_null_fields_safety(self):
        """Test that IGDB provider handles null values for optional fields without crashing."""
        provider = IGDBProvider.__new__(IGDBProvider)
        null_data = {
            "id": 123,
            "name": "Test Game",
            "cover": None,
            "involved_companies": None,
            "genres": None,
            "themes": None,
            "game_modes": None,
            "multiplayer_modes": None,
            "status": None
        }
        unified = provider._map_to_unified(null_data)
        self.assertEqual(unified.name, "Test Game")
        self.assertIsNone(unified.cover_url)
        self.assertEqual(unified.developers, [])
        self.assertEqual(unified.genres, [])

    def test_rawg_zero_playtime_maps_to_none(self):
        """Test that RAWG provider converts playtime of 0 to None."""
        provider = RAWGProvider.__new__(RAWGProvider)
        raw_data = {
            "id": 456,
            "name": "Zero Playtime Game",
            "playtime": 0
        }
        unified = provider._map_to_unified(raw_data)
        self.assertIsNone(unified.playtime_hours)

if __name__ == "__main__":
    unittest.main()