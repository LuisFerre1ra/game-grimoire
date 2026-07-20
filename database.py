"""SQLite persistence for the local game library."""

from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator, Sequence

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "game_library.db"

DEFAULT_TAGS = [
    ("Early Access", "Status", "#E0A84A"),
    ("Negative Reviews", "Reviews", "#D95D5D"),
    ("Mixed Reviews", "Reviews", "#DB8B4A"),
    ("Mod Required", "Requirement", "#8E6CD1"),
    ("Multiplayer", "Mode", "#4389D7"),
    ("Unreleased", "Status", "#8C8C8C"),
    ("Incomplete Content", "Status", "#A8745A"),
    ("Unplayable", "Compatibility", "#CC4F6A"),
    ("Uncategorized", "Other", "#7E8996"),
]


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def normalize_title(value: str) -> str:
    """Produce a stable, accent-insensitive comparison key for a title."""
    decomposed = unicodedata.normalize("NFKD", value)
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", without_accents.lower()).strip()


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    DATA_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_database() -> None:
    """Create the schema and the small starter tag catalogue if needed."""
    with connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                category TEXT NOT NULL DEFAULT 'Other',
                color TEXT NOT NULL DEFAULT '#7E8996',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS games (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                normalized_title TEXT NOT NULL COLLATE NOCASE UNIQUE,
                status TEXT NOT NULL DEFAULT 'backlog'
                    CHECK(status IN ('backlog', 'played', 'abandoned')),
                ready_to_play INTEGER NOT NULL DEFAULT 0 CHECK(ready_to_play IN (0, 1)),
                notes TEXT,
                added_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                rawg_id INTEGER,
                rawg_slug TEXT,
                release_date TEXT,
                cover_local_path TEXT,
                cover_source_url TEXT,
                developers_json TEXT,
                genres_json TEXT,
                rawg_tags_json TEXT,
                metadata_source TEXT,
                metadata_updated_at TEXT,
                external_metadata_json TEXT
            );

            CREATE TABLE IF NOT EXISTS game_tags (
                game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
                tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE RESTRICT,
                PRIMARY KEY(game_id, tag_id)
            );

            CREATE TABLE IF NOT EXISTS playtime_estimates (
                id INTEGER PRIMARY KEY,
                game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
                source TEXT NOT NULL,
                metric TEXT NOT NULL DEFAULT 'historia_principal',
                hours REAL CHECK(hours IS NULL OR hours > 0),
                result_status TEXT NOT NULL DEFAULT 'found'
                    CHECK(result_status IN ('found', 'not_found', 'error', 'needs_review')),
                query_title TEXT,
                matched_title TEXT,
                confidence REAL,
                source_url TEXT,
                raw_payload_json TEXT,
                selected INTEGER NOT NULL DEFAULT 0 CHECK(selected IN (0, 1)),
                retrieved_at TEXT NOT NULL
            );

            CREATE UNIQUE INDEX IF NOT EXISTS one_selected_estimate_per_game
                ON playtime_estimates(game_id) WHERE selected = 1;

            CREATE TABLE IF NOT EXISTS play_events (
                id INTEGER PRIMARY KEY,
                game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
                outcome TEXT NOT NULL CHECK(outcome IN ('completed', 'abandoned')),
                played_year INTEGER CHECK(played_year BETWEEN 1900 AND 2200),
                played_at TEXT,
                notes TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS game_history (
                id INTEGER PRIMARY KEY,
                game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
                event_type TEXT NOT NULL,
                details_json TEXT,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_games_status ON games(status);
            CREATE INDEX IF NOT EXISTS idx_games_added_at ON games(added_at);
            CREATE INDEX IF NOT EXISTS idx_play_events_game ON play_events(game_id);
            """
        )
        conn.execute(
            "INSERT OR IGNORE INTO schema_meta(key, value) VALUES ('schema_version', '1')"
        )
        stamp = now_iso()
        conn.executemany(
            """
            INSERT OR IGNORE INTO tags(name, category, color, created_at)
            VALUES (?, ?, ?, ?)
            """,
            [(name, category, color, stamp) for name, category, color in DEFAULT_TAGS],
        )


def _row_to_game(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["ready_to_play"] = bool(item["ready_to_play"])
    tags_text = item.pop("tags_text", "") or ""
    years_text = item.pop("years_text", "") or ""
    item["tags"] = tags_text.split(",") if tags_text else []
    item["years"] = [int(value) for value in years_text.split(",") if value]
    return item


def list_games(statuses: Sequence[str] | None = None) -> list[dict[str, Any]]:
    clauses: list[str] = []
    parameters: list[Any] = []
    if statuses:
        placeholders = ",".join("?" for _ in statuses)
        clauses.append(f"g.status IN ({placeholders})")
        parameters.extend(statuses)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    query = f"""
        SELECT
            g.*,
            estimate.hours AS hours,
            estimate.source AS hours_source,
            GROUP_CONCAT(DISTINCT t.name) AS tags_text,
            GROUP_CONCAT(DISTINCT pe.played_year) AS years_text
        FROM games g
        LEFT JOIN playtime_estimates estimate
            ON estimate.game_id = g.id AND estimate.selected = 1
        LEFT JOIN game_tags gt ON gt.game_id = g.id
        LEFT JOIN tags t ON t.id = gt.tag_id
        LEFT JOIN play_events pe ON pe.game_id = g.id
        {where}
        GROUP BY g.id
    """
    with connection() as conn:
        return [_row_to_game(row) for row in conn.execute(query, parameters).fetchall()]


def get_game(game_id: int) -> dict[str, Any] | None:
    games = [game for game in list_games() if game["id"] == game_id]
    return games[0] if games else None


def get_game_tags(game_id: int) -> list[int]:
    with connection() as conn:
        rows = conn.execute(
            "SELECT tag_id FROM game_tags WHERE game_id = ? ORDER BY tag_id", (game_id,)
        ).fetchall()
    return [row["tag_id"] for row in rows]


def list_tags() -> list[dict[str, Any]]:
    with connection() as conn:
        return [
            dict(row)
            for row in conn.execute("SELECT * FROM tags ORDER BY category, name").fetchall()
        ]


def add_tag(name: str, category: str = "Other", color: str = "#7E8996") -> None:
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("Tag requires a name.")
    with connection() as conn:
        conn.execute(
            "INSERT INTO tags(name, category, color, created_at) VALUES (?, ?, ?, ?)",
            (clean_name, category.strip() or "Other", color, now_iso()),
        )


def update_tag(tag_id: int, name: str, category: str, color: str) -> None:
    if not name.strip():
        raise ValueError("Tag requires a name.")
    with connection() as conn:
        conn.execute(
            "UPDATE tags SET name = ?, category = ?, color = ? WHERE id = ?",
            (name.strip(), category.strip() or "Other", color, tag_id),
        )


def delete_tag(tag_id: int) -> None:
    with connection() as conn:
        conn.execute("DELETE FROM game_tags WHERE tag_id = ?", (tag_id,))
        conn.execute("DELETE FROM tags WHERE id = ?", (tag_id,))


def create_game(
    title: str,
    status: str = "backlog",
    ready_to_play: bool = False,
    notes: str | None = None,
    tag_ids: Sequence[int] = (),
) -> int:
    clean_title = title.strip()
    if not clean_title:
        raise ValueError("El título no puede estar vacío.")
    if status not in {"backlog", "played", "abandoned"}:
        raise ValueError("Status no válido.")
    stamp = now_iso()
    with connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO games(title, normalized_title, status, ready_to_play, notes, added_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                clean_title,
                normalize_title(clean_title),
                status,
                int(ready_to_play),
                notes.strip() if notes else None,
                stamp,
                stamp,
            ),
        )
        game_id = int(cursor.lastrowid)
        _set_game_tags(conn, game_id, tag_ids)
        _history(conn, game_id, "created", {"status": status})
    return game_id


def _set_game_tags(conn: sqlite3.Connection, game_id: int, tag_ids: Sequence[int]) -> None:
    conn.execute("DELETE FROM game_tags WHERE game_id = ?", (game_id,))
    conn.executemany(
        "INSERT OR IGNORE INTO game_tags(game_id, tag_id) VALUES (?, ?)",
        [(game_id, tag_id) for tag_id in tag_ids],
    )


def update_game(
    game_id: int,
    *,
    title: str,
    ready_to_play: bool,
    notes: str | None,
    tag_ids: Sequence[int],
) -> None:
    clean_title = title.strip()
    if not clean_title:
        raise ValueError("El título no puede estar vacío.")
    with connection() as conn:
        conn.execute(
            """
            UPDATE games
            SET title = ?, normalized_title = ?, ready_to_play = ?, notes = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                clean_title,
                normalize_title(clean_title),
                int(ready_to_play),
                notes.strip() if notes else None,
                now_iso(),
                game_id,
            ),
        )
        _set_game_tags(conn, game_id, tag_ids)
        _history(conn, game_id, "edited", {"title": clean_title})


def add_or_select_estimate(
    game_id: int,
    hours: float | None,
    source: str = "Manual",
    metric: str = "historia_principal",
    result_status: str = "found",
    matched_title: str | None = None,
    confidence: float | None = None,
    source_url: str | None = None,
) -> None:
    if hours is not None and hours <= 0:
        raise ValueError("Hours must be greater than zero.")
    with connection() as conn:
        conn.execute("UPDATE playtime_estimates SET selected = 0 WHERE game_id = ?", (game_id,))
        conn.execute(
            """
            INSERT INTO playtime_estimates(
                game_id, source, metric, hours, result_status, matched_title,
                confidence, source_url, selected, retrieved_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (
                game_id,
                source,
                metric,
                hours,
                result_status,
                matched_title,
                confidence,
                source_url,
                now_iso(),
            ),
        )
        _history(conn, game_id, "playtime_updated", {"hours": hours, "source": source})


def clear_selected_estimate(game_id: int) -> None:
    """Keep prior estimates as history but leave the game without an active duration."""
    with connection() as conn:
        conn.execute("UPDATE playtime_estimates SET selected = 0 WHERE game_id = ?", (game_id,))
        _history(conn, game_id, "playtime_cleared", {})


def change_status(
    game_id: int, status: str, played_year: int | None = None, notes: str | None = None
) -> None:
    if status not in {"backlog", "played", "abandoned"}:
        raise ValueError("Status no válido.")
    with connection() as conn:
        conn.execute(
            "UPDATE games SET status = ?, updated_at = ? WHERE id = ?",
            (status, now_iso(), game_id),
        )
        if status in {"played", "abandoned"}:
            conn.execute(
                """
                INSERT INTO play_events(game_id, outcome, played_year, notes, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    game_id,
                    "completed" if status == "played" else "abandoned",
                    played_year,
                    notes.strip() if notes else None,
                    now_iso(),
                ),
            )
        _history(conn, game_id, "status_changed", {"status": status, "year": played_year})


def delete_game(game_id: int) -> None:
    with connection() as conn:
        conn.execute("DELETE FROM games WHERE id = ?", (game_id,))


def update_game_metadata(game_id: int, metadata: dict[str, Any], local_cover_path: str | None) -> None:
    developers = [item.get("name") for item in metadata.get("developers", []) if item.get("name")]
    genres = [item.get("name") for item in metadata.get("genres", []) if item.get("name")]
    rawg_tags = [item.get("name") for item in metadata.get("tags", []) if item.get("name")]
    with connection() as conn:
        conn.execute(
            """
            UPDATE games SET
                rawg_id = ?, rawg_slug = ?, release_date = ?,
                cover_local_path = COALESCE(?, cover_local_path),
                cover_source_url = ?, developers_json = ?, genres_json = ?, rawg_tags_json = ?,
                metadata_source = 'RAWG', metadata_updated_at = ?, external_metadata_json = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                metadata.get("id"),
                metadata.get("slug"),
                metadata.get("released"),
                local_cover_path,
                metadata.get("background_image"),
                json.dumps(developers, ensure_ascii=False),
                json.dumps(genres, ensure_ascii=False),
                json.dumps(rawg_tags, ensure_ascii=False),
                now_iso(),
                json.dumps(metadata, ensure_ascii=False),
                now_iso(),
                game_id,
            ),
        )
        _history(conn, game_id, "metadata_updated", {"source": "RAWG"})


def _history(conn: sqlite3.Connection, game_id: int, event_type: str, details: dict[str, Any]) -> None:
    conn.execute(
        "INSERT INTO game_history(game_id, event_type, details_json, created_at) VALUES (?, ?, ?, ?)",
        (game_id, event_type, json.dumps(details, ensure_ascii=False), now_iso()),
    )


def get_setting(key: str, default: str = "") -> str:
    with connection() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO settings(key, value, updated_at) VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (key, value, now_iso()),
        )


def dashboard_metrics() -> dict[str, Any]:
    games = list_games()
    backlog = [item for item in games if item["status"] == "backlog"]
    known = [float(item["hours"]) for item in backlog if item["hours"] is not None]
    missing = len(backlog) - len(known)
    known_sum = sum(known)
    predicted_total: float | None = None
    margin: float | None = None
    if missing and len(known) > 1:
        mean = known_sum / len(known)
        variance = sum((value - mean) ** 2 for value in known) / (len(known) - 1)
        standard_deviation = variance**0.5
        predicted_total = known_sum + missing * mean
        margin = 1.28 * standard_deviation * (missing + (missing**2 / len(known))) ** 0.5
    elif not missing:
        predicted_total = known_sum
        margin = 0
    return {
        "backlog": len(backlog),
        "ready": sum(1 for item in backlog if item["ready_to_play"]),
        "played": sum(1 for item in games if item["status"] == "played"),
        "abandoned": sum(1 for item in games if item["status"] == "abandoned"),
        "known_hours": known_sum,
        "unknown_hours": missing,
        "predicted_hours": predicted_total,
        "margin_hours": margin,
    }


def export_rows() -> list[dict[str, Any]]:
    rows = list_games()
    for row in rows:
        row["tags"] = ", ".join(row["tags"])
        row["years"] = ", ".join(str(year) for year in sorted(set(row["years"])))
    return rows
