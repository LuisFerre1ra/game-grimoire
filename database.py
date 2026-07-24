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

from interfaces import UnifiedGameData

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "game_library.db"

DEFAULT_TAGS = [
    ("Early Access", "Status", "#E0A84A", 1),
    ("Multiplayer", "Mode", "#4389D7", 0),
    ("Unreleased", "Status", "#8C8C8C", 1),
    ("Incomplete Content", "Status", "#A8745A", 1),
]

def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()

def normalize_title(value: str) -> str:
    """Generate normalized title key for comparison."""
    decomposed = unicodedata.normalize("NFKD", value)
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", without_accents.lower()).strip()

_conn: sqlite3.Connection | None = None

def _get_connection() -> sqlite3.Connection:
    """Return a long-lived module-level connection (created once, reused)."""
    global _conn
    if _conn is None:
        DATA_DIR.mkdir(exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA foreign_keys = ON")
        _conn.execute("PRAGMA journal_mode = WAL")
    return _conn

@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    conn = _get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise

def init_database() -> None:
    """Initialize database schema and default tags."""
    with connection() as conn:
        conn.executescript(
            """

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
                is_custom INTEGER NOT NULL DEFAULT 0 CHECK(is_custom IN (0, 1)),
                is_main INTEGER NOT NULL DEFAULT 0 CHECK(is_main IN (0, 1)),
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tag_aliases (
                id INTEGER PRIMARY KEY,
                alias_name TEXT NOT NULL COLLATE NOCASE,
                tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
                UNIQUE(alias_name, tag_id)
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
                release_date TEXT,
                cover_local_path TEXT,
                cover_source_url TEXT,
                metadata_source TEXT,
                metadata_updated_at TEXT,
                developer_info_json TEXT
            );

            CREATE TABLE IF NOT EXISTS game_tags (
                game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
                tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
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
            CREATE INDEX IF NOT EXISTS idx_tag_aliases_name ON tag_aliases(alias_name);
            CREATE INDEX IF NOT EXISTS idx_game_tags_tag ON game_tags(tag_id);

            CREATE TABLE IF NOT EXISTS game_provider_data (
                id INTEGER PRIMARY KEY,
                game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
                provider_name TEXT NOT NULL,
                provider_game_id TEXT NOT NULL,
                raw_payload_json TEXT,
                fetched_at TEXT NOT NULL,
                UNIQUE(game_id, provider_name)
            );
            """
        )
        stamp = now_iso()
        conn.executemany(
            """
            INSERT OR IGNORE INTO tags(name, category, color, is_main, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            [(name, category, color, is_main, stamp) for name, category, color, is_main in DEFAULT_TAGS],
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
            (
                SELECT GROUP_CONCAT(t.name)
                FROM game_tags gt
                JOIN tags t ON t.id = gt.tag_id
                WHERE gt.game_id = g.id
            ) AS tags_text,
            (
                SELECT GROUP_CONCAT(DISTINCT pe.played_year)
                FROM play_events pe
                WHERE pe.game_id = g.id AND pe.played_year IS NOT NULL
            ) AS years_text
        FROM games g
        LEFT JOIN playtime_estimates estimate
            ON estimate.game_id = g.id AND estimate.selected = 1
        {where}
    """
    with connection() as conn:
        return [_row_to_game(row) for row in conn.execute(query, parameters).fetchall()]

def get_game(game_id: int) -> dict[str, Any] | None:
    query = """
        SELECT
            g.*,
            estimate.hours AS hours,
            estimate.source AS hours_source,
            (
                SELECT GROUP_CONCAT(t.name)
                FROM game_tags gt
                JOIN tags t ON t.id = gt.tag_id
                WHERE gt.game_id = g.id
            ) AS tags_text,
            (
                SELECT GROUP_CONCAT(DISTINCT pe.played_year)
                FROM play_events pe
                WHERE pe.game_id = g.id AND pe.played_year IS NOT NULL
            ) AS years_text
        FROM games g
        LEFT JOIN playtime_estimates estimate
            ON estimate.game_id = g.id AND estimate.selected = 1
        WHERE g.id = ?
    """
    with connection() as conn:
        row = conn.execute(query, (game_id,)).fetchone()
    return _row_to_game(row) if row else None

def get_game_tags(game_id: int) -> list[int]:
    with connection() as conn:
        rows = conn.execute(
            "SELECT tag_id FROM game_tags WHERE game_id = ? ORDER BY tag_id", (game_id,)
        ).fetchall()
    return [row["tag_id"] for row in rows]

def list_tags() -> list[dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT t.*, GROUP_CONCAT(a.alias_name) AS aliases_text
            FROM tags t
            LEFT JOIN tag_aliases a ON a.tag_id = t.id
            GROUP BY t.id
            ORDER BY t.category, t.name
            """
        ).fetchall()
        result = []
        for row in rows:
            tag_dict = dict(row)
            aliases_text = tag_dict.pop("aliases_text", None) or ""
            tag_dict["aliases"] = ", ".join(sorted(set(a.strip() for a in aliases_text.split(",") if a.strip())))
            result.append(tag_dict)
        return result

def get_or_create_tag(name: str, category: str = "Other", color: str = "#7E8996", is_custom: bool = False, is_main: bool = False) -> int:
    """Get or create custom user tag."""
    clean_name = name.strip()
    with connection() as conn:
        row = conn.execute("SELECT id FROM tags WHERE name = ?", (clean_name,)).fetchone()
        if row:
            return row["id"]
        cursor = conn.execute(
            "INSERT INTO tags(name, category, color, is_custom, is_main, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (clean_name, category, color, int(is_custom), int(is_main), now_iso())
        )
        return cursor.lastrowid

def _clear_tags_cache_safe() -> None:
    try:
        from ui_helpers import clear_tags_cache
        clear_tags_cache()
    except Exception:
        pass

def resolve_tags_via_aliases(raw_names: list[str]) -> set[int]:
    """Look up raw provider tag names via tags table or tag_aliases table.

    Returns the set of tag IDs that matched. Unknown names are silently
    skipped — no new tags are ever created by this function.
    """
    cleaned = [n.strip().lower() for n in raw_names if n and n.strip()]
    if not cleaned:
        return set()
    placeholders = ",".join(["?"] * len(cleaned))
    with connection() as conn:
        rows_alias = conn.execute(
            f"SELECT DISTINCT a.tag_id FROM tag_aliases a WHERE LOWER(a.alias_name) IN ({placeholders})",
            cleaned,
        ).fetchall()
        rows_direct = conn.execute(
            f"SELECT DISTINCT t.id AS tag_id FROM tags t WHERE LOWER(t.name) IN ({placeholders})",
            cleaned,
        ).fetchall()
    matched = {r["tag_id"] for r in rows_alias}
    matched.update(r["tag_id"] for r in rows_direct)
    return matched

def add_tag(name: str, category: str = "Other", color: str = "#7E8996", is_main: bool = False) -> None:
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("Tag requires a name.")
    with connection() as conn:
        conn.execute(
            "INSERT INTO tags(name, category, color, is_custom, is_main, created_at) VALUES (?, ?, ?, 1, ?, ?)",
            (clean_name, category.strip() or "Other", color, int(is_main), now_iso()),
        )
    _clear_tags_cache_safe()

def update_tag(tag_id: int, name: str, category: str, color: str, is_main: bool = False, aliases: str = "") -> None:
    if not name.strip():
        raise ValueError("Tag requires a name.")
    with connection() as conn:
        conn.execute(
            "UPDATE tags SET name = ?, category = ?, color = ?, is_main = ? WHERE id = ?",
            (name.strip(), category.strip() or "Other", color, int(is_main), tag_id),
        )
        conn.execute("DELETE FROM tag_aliases WHERE tag_id = ?", (tag_id,))
        alias_list = [a.strip().lower() for a in aliases.split(",") if a.strip()]
        for alias in set(alias_list):
            conn.execute("INSERT OR IGNORE INTO tag_aliases(alias_name, tag_id) VALUES (?, ?)", (alias, tag_id))
    _clear_tags_cache_safe()

def delete_tag(tag_id: int) -> None:
    with connection() as conn:
        conn.execute("DELETE FROM game_tags WHERE tag_id = ?", (tag_id,))
        conn.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
    _clear_tags_cache_safe()

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
    conn.execute(
        "DELETE FROM game_tags WHERE game_id = ? AND tag_id IN (SELECT id FROM tags WHERE is_custom = 1)",
        (game_id,)
    )
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

def update_game_metadata(
    game_id: int, 
    unified: UnifiedGameData, 
    raw_payload: str, 
    provider_name: str, 
    local_cover_path: str | None
) -> None:
    # Resolve provider tags via aliases
    # Skip unrecognized tags
    raw_tag_names: list[str] = []
    raw_tag_names.extend(unified.genres)
    raw_tag_names.extend(unified.themes)
    raw_tag_names.extend(
        gm for gm in unified.game_modes
        if gm.lower() not in {"multiplayer", "multiplayedr"}
    )
    raw_tag_names.extend(unified.multiplayer_modes)
    if unified.game_status:
        raw_tag_names.append(unified.game_status)
    tag_ids = resolve_tags_via_aliases(raw_tag_names)

    stamp = now_iso()
    with connection() as conn:
        conn.execute(
            """
            UPDATE games SET
                release_date = COALESCE(?, release_date),
                cover_local_path = COALESCE(?, cover_local_path),
                cover_source_url = COALESCE(?, cover_source_url),
                developer_info_json = ?,
                metadata_source = ?,
                metadata_updated_at = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                unified.first_release_date,
                local_cover_path,
                unified.cover_url,
                json.dumps({"developers": unified.developers, "publishers": unified.publishers}, ensure_ascii=False),
                provider_name,
                stamp,
                stamp,
                game_id,
            ),
        )
        
        conn.execute(
            """
            INSERT INTO game_provider_data(game_id, provider_name, provider_game_id, raw_payload_json, fetched_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(game_id, provider_name) DO UPDATE SET
                provider_game_id = excluded.provider_game_id,
                raw_payload_json = excluded.raw_payload_json,
                fetched_at = excluded.fetched_at
            """,
            (game_id, provider_name, unified.provider_id, raw_payload, stamp)
        )
        
        # Refresh provider tags while preserving user tags
        conn.execute(
            "DELETE FROM game_tags WHERE game_id = ? AND tag_id IN (SELECT id FROM tags WHERE is_custom = 0)",
            (game_id,)
        )
        for tid in tag_ids:
            conn.execute("INSERT OR IGNORE INTO game_tags(game_id, tag_id) VALUES (?, ?)", (game_id, tid))
        
        _history(conn, game_id, "metadata_updated", {"source": provider_name})
    _clear_tags_cache_safe()

def clear_game_metadata(game_id: int) -> None:
    with connection() as conn:
        conn.execute(
            """
            UPDATE games SET
                release_date = NULL,
                cover_local_path = NULL, cover_source_url = NULL,
                developer_info_json = NULL,
                metadata_source = NULL, metadata_updated_at = NULL,
                updated_at = ?
            WHERE id = ?
            """,
            (now_iso(), game_id),
        )
        conn.execute("DELETE FROM game_provider_data WHERE game_id = ?", (game_id,))
        conn.execute(
            "DELETE FROM game_tags WHERE game_id = ? AND tag_id IN (SELECT id FROM tags WHERE is_custom = 0)",
            (game_id,)
        )
        _history(conn, game_id, "metadata_cleared", {})
    _clear_tags_cache_safe()

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
    with connection() as conn:
        counts = conn.execute(
            """
            SELECT
                SUM(CASE WHEN status = 'backlog' THEN 1 ELSE 0 END) AS backlog,
                SUM(CASE WHEN status = 'backlog' AND ready_to_play = 1 THEN 1 ELSE 0 END) AS ready,
                SUM(CASE WHEN status = 'played' THEN 1 ELSE 0 END) AS played,
                SUM(CASE WHEN status = 'abandoned' THEN 1 ELSE 0 END) AS abandoned
            FROM games
            """
        ).fetchone()
        hours_row = conn.execute(
            """
            SELECT
                COUNT(e.hours) AS known_count,
                COALESCE(SUM(e.hours), 0) AS known_sum
            FROM games g
            LEFT JOIN playtime_estimates e ON e.game_id = g.id AND e.selected = 1
            WHERE g.status = 'backlog'
            """
        ).fetchone()
    backlog_count = counts["backlog"] or 0
    known_count = hours_row["known_count"] or 0
    known_sum = hours_row["known_sum"] or 0
    missing = backlog_count - known_count
    predicted_total: float | None = None
    margin: float | None = None
    if missing and known_count > 1:
        # For variance we still need the individual values
        with connection() as conn:
            values = [r[0] for r in conn.execute(
                "SELECT e.hours FROM games g JOIN playtime_estimates e ON e.game_id = g.id AND e.selected = 1 WHERE g.status = 'backlog' AND e.hours IS NOT NULL"
            ).fetchall()]
        mean = known_sum / known_count
        variance = sum((v - mean) ** 2 for v in values) / (known_count - 1)
        standard_deviation = variance**0.5
        predicted_total = known_sum + missing * mean
        margin = 1.28 * standard_deviation * (missing + (missing**2 / known_count)) ** 0.5
    elif not missing:
        predicted_total = known_sum
        margin = 0
    return {
        "backlog": backlog_count,
        "ready": counts["ready"] or 0,
        "played": counts["played"] or 0,
        "abandoned": counts["abandoned"] or 0,
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

# Cleanup utilities

_DEFAULT_TAG_NAMES = frozenset(name for name, *_ in DEFAULT_TAGS)

def cleanup_spurious_tags() -> int:
    """Delete non-custom tags that were created by the old buggy enrichment.

    A tag is considered spurious if:
      • is_custom = 0  (not user-created)
      • its name is NOT in DEFAULT_TAGS  (not a seeded tag)
      • it has NO aliases in tag_aliases  (not part of the curated taxonomy)

    Returns the number of tags deleted.
    """
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT t.id, t.name
            FROM tags t
            LEFT JOIN tag_aliases a ON a.tag_id = t.id
            WHERE t.is_custom = 0
            GROUP BY t.id
            HAVING COUNT(a.id) = 0
            """
        ).fetchall()
        spurious = [r for r in rows if r["name"] not in _DEFAULT_TAG_NAMES]
        if not spurious:
            return 0
        ids = [r["id"] for r in spurious]
        placeholders = ",".join("?" for _ in ids)
        conn.execute(f"DELETE FROM game_tags WHERE tag_id IN ({placeholders})", ids)
        conn.execute(f"DELETE FROM tags WHERE id IN ({placeholders})", ids)
    return len(spurious)

def cleanup_orphan_covers() -> int:
    """Delete cover image files not referenced by any game.  Returns count deleted."""
    covers_dir = DATA_DIR / "covers"
    if not covers_dir.exists():
        return 0
    with connection() as conn:
        rows = conn.execute(
            "SELECT cover_local_path FROM games WHERE cover_local_path IS NOT NULL"
        ).fetchall()
    referenced = set()
    for r in rows:
        path = r["cover_local_path"]
        if path:
            referenced.add(Path(path).name)
    deleted = 0
    for f in covers_dir.iterdir():
        if f.is_file() and f.name not in referenced:
            f.unlink()
            deleted += 1
    return deleted