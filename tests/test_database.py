"""Unit tests for SQLite database persistence module."""

import unittest
import shutil
import tempfile
import sys
from pathlib import Path

# Add project src/ directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import database as db
from interfaces import GameStatus

class TestDatabase(unittest.TestCase):
    def setUp(self):
        """Use a temporary directory and database file for isolation."""
        self.temp_dir = tempfile.mkdtemp()
        self.tmp_path = Path(self.temp_dir)
        self.test_db_path = self.tmp_path / "test_game_library.db"
        self.test_data_dir = self.tmp_path / "data"
        self.test_data_dir.mkdir(exist_ok=True)

        self.orig_conn = db._conn
        self.orig_db_path = db.DB_PATH
        self.orig_data_dir = db.DATA_DIR

        db._conn = None
        db.DB_PATH = self.test_db_path
        db.DATA_DIR = self.test_data_dir

        db.init_database()

    def tearDown(self):
        if db._conn:
            db._conn.close()
            db._conn = None
        db.DB_PATH = self.orig_db_path
        db.DATA_DIR = self.orig_data_dir
        db._conn = self.orig_conn
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_normalize_title(self):
        """Test title normalization with accents, special chars, and case."""
        self.assertEqual(db.normalize_title("Super Mario Bros."), "super mario bros")
        self.assertEqual(db.normalize_title("  Pokémon   Emerald!  "), "pokemon emerald")
        self.assertEqual(db.normalize_title("The Witcher 3: Wild Hunt"), "the witcher 3 wild hunt")
        self.assertEqual(db.normalize_title("Cōde: Realize ~Guardian of Rebirth~"), "code realize guardian of rebirth")

    def test_create_and_get_game(self):
        """Test creating a game and fetching it by ID."""
        game_id = db.create_game(
            title="Hollow Knight",
            status="backlog",
            ready_to_play=True,
            notes="Metroidvania masterpiece",
            hours=25.5
        )
        self.assertIsNotNone(game_id)
        self.assertGreater(game_id, 0)

        game = db.get_game(game_id)
        self.assertIsNotNone(game)
        self.assertEqual(game["title"], "Hollow Knight")
        self.assertEqual(game["normalized_title"], "hollow knight")
        self.assertEqual(game["status"], "backlog")
        self.assertEqual(game["ready_to_play"], 1)
        self.assertEqual(game["notes"], "Metroidvania masterpiece")
        self.assertEqual(game["hours"], 25.5)

    def test_unique_normalized_title(self):
        """Test that creating duplicate titles raises an exception."""
        db.create_game(title="Portal 2")
        with self.assertRaises(Exception):
            db.create_game(title="portal 2")

    def test_update_and_delete_game(self):
        """Test updating game info and deleting games."""
        game_id = db.create_game(title="Celeste", status="backlog")

        # Update game
        db.update_game(
            game_id,
            title="Celeste Deluxe",
            ready_to_play=True,
            notes="Updated notes",
            tag_ids=[],
            hours=15.0
        )
        updated = db.get_game(game_id)
        self.assertEqual(updated["title"], "Celeste Deluxe")
        self.assertEqual(updated["notes"], "Updated notes")
        self.assertEqual(updated["hours"], 15.0)

        # Delete game
        db.delete_game(game_id)
        self.assertIsNone(db.get_game(game_id))

    def test_change_status(self):
        """Test game status transition logic."""
        game_id = db.create_game(title="Elden Ring", status="backlog")

        db.change_status(game_id, "played")
        game = db.get_game(game_id)
        self.assertEqual(game["status"], "played")

        db.change_status(game_id, "abandoned")
        game = db.get_game(game_id)
        self.assertEqual(game["status"], "abandoned")

    def test_tags_and_aliases(self):
        """Test creating tags, getting tags, and alias lookup."""
        tag_id = db.get_or_create_tag("Indie", category="Genres", color="#FF5733")
        self.assertGreater(tag_id, 0)

        game_id = db.create_game(title="Dead Cells", tag_ids=[tag_id])

        tags = db.get_game_tags(game_id)
        self.assertIn(tag_id, tags)

        tag_details = db.get_game_tags_with_categories(game_id)
        tag_names = [t["name"] for t in tag_details]
        self.assertIn("Indie", tag_names)

        # Delete tag should cascade
        db.delete_tag(tag_id)
        self.assertNotIn(tag_id, db.get_game_tags(game_id))

    def test_update_game_tags_allows_adding_and_removing_all_tags(self):
        """Test that updating a game allows replacing all tag IDs (default or custom)."""
        tag1 = db.get_or_create_tag("RPG", category="Genres", is_custom=False)
        tag2 = db.get_or_create_tag("Favorite", category="Personal", is_custom=True)
        tag3 = db.get_or_create_tag("Strategy", category="Genres", is_custom=False)

        game_id = db.create_game(title="Strategy RPG", tag_ids=[tag1, tag2])
        self.assertCountEqual(db.get_game_tags(game_id), [tag1, tag2])

        # Remove tag1 and tag2, add tag3
        db.update_game(game_id, title="Strategy RPG", ready_to_play=False, notes=None, tag_ids=[tag3])
        self.assertCountEqual(db.get_game_tags(game_id), [tag3])

    def test_settings(self):
        """Test getting and setting key-value configuration settings."""
        db.set_setting("rawg_api_key", "test_key_123")
        self.assertEqual(db.get_setting("rawg_api_key"), "test_key_123")
        self.assertEqual(db.get_setting("non_existent_key"), "")
        self.assertIsNone(db.get_setting("non_existent_key", default=None))

    def test_schema_version(self):
        """Test reading and setting database schema version."""
        self.assertEqual(db.get_schema_version(), 1)
        with db.connection() as conn:
            db.set_schema_version(conn, 2)
        self.assertEqual(db.get_schema_version(), 2)

    def test_update_game_metadata_zero_hours_safety(self):
        """Test that update_game_metadata with playtime_hours=0 does not violate CHECK constraint."""
        from interfaces import UnifiedGameData
        game_id = db.create_game(title="Hades")
        unified = UnifiedGameData(
            provider_id="123",
            name="Hades",
            playtime_hours=0.0
        )
        db.update_game_metadata(game_id, unified, "{}", "RAWG", None)
        game = db.get_game(game_id)
        self.assertIsNone(game["hours"])

if __name__ == "__main__":
    unittest.main()