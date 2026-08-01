from __future__ import annotations
import json
from datetime import datetime
from typing import Any
import streamlit as st
import database as db
from interfaces import GameStatus
from providers import ProviderError, cache_cover, get_ordered_providers
from ui_helpers import cached_list_tags

def enrich_one(game_id: int, title: str) -> str:
    providers = get_ordered_providers()
    if not providers:
        return "No providers configured."
        
    last_error = ""
    for provider in providers:
        try:
            results = provider.search(title)
            if results:
                best = results[0]
                unified, raw = provider.fetch_details(best.provider_id)
                local_cover = None
                try:
                    local_cover = cache_cover(unified.cover_url, game_id)
                except Exception:
                    pass
                db.update_game_metadata(game_id, unified, json.dumps(raw, ensure_ascii=False), provider.get_name(), local_cover)
                return f"Updated from {provider.get_name()}."
        except ProviderError as exc:
            last_error = f"{provider.get_name()} error: {exc}"
            continue
        except Exception as exc:
            last_error = f"{provider.get_name()} unexpected error: {exc}"
            continue
    return last_error or "No matches found in any provider."

def add_games_page() -> None:
    st.title("Add Games")
    st.write("Paste one title per line. Duplicates are detected by normalized title.")
    tags = cached_list_tags()
    custom_tags = [t for t in tags if t["is_custom"]]
    label_to_id = {tag["name"]: tag["id"] for tag in custom_tags}
    has_providers = bool(get_ordered_providers())
    with st.form("add_games"):
        titles = st.text_area("Titles", height=220, placeholder="Hades\nOuter Wilds\nBalatro")
        destination = st.radio("Add to", ["Backlog", "Played", "Abandoned"], horizontal=True)
        selected_tags = st.multiselect("Initial Tags", list(label_to_id))
        ready = st.checkbox("Mark as ready to play", disabled=destination != "Backlog")
        enrich = st.checkbox("Auto-fetch details", value=has_providers, disabled=not has_providers)
        submitted = st.form_submit_button("Add Games", type="primary")
    if not submitted:
        return
    requested = [line.strip() for line in titles.splitlines() if line.strip()]
    if not requested:
        st.warning("Please add at least one title.")
        return
    status_map = {"Backlog": GameStatus.BACKLOG, "Played": GameStatus.PLAYED, "Abandoned": GameStatus.ABANDONED}
    status = status_map[destination]
    existing = db.get_all_normalized_titles()
    created: list[tuple[int, str]] = []
    skipped: list[str] = []
    for title in requested:
        normalized = db.normalize_title(title)
        if normalized in existing:
            skipped.append(title)
            continue
        game_id = db.create_game(title, status=status, ready_to_play=ready if status == GameStatus.BACKLOG else False, tag_ids=[label_to_id[name] for name in selected_tags])
        if status in {GameStatus.PLAYED, GameStatus.ABANDONED}:
            outcome = "completed" if status == GameStatus.PLAYED else "abandoned"
            db.add_play_event(game_id, outcome, datetime.now().year)
        existing.add(normalized)
        created.append((game_id, title))
    messages: list[str] = []
    if enrich and created:
        progress = st.progress(0, text="Searching metadata in providers...")
        for number, (game_id, title) in enumerate(created, start=1):
            messages.append(f"{title}: {enrich_one(game_id, title)}")
            progress.progress(number / len(created), text=f"Enriching {number} of {len(created)}...")
        progress.empty()
        cached_list_tags.clear()

    if created:
        st.toast(f"Added {len(created)} game(s)", icon=":material/check_circle:")
    if skipped:
        st.info(f"Skipped duplicates: {', '.join(skipped)}")
    if messages:
        with st.expander("Enrichment Result"):
            st.write("\n\n".join(messages))