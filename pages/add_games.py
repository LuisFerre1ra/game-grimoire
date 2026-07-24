from __future__ import annotations
import json
from datetime import datetime
from typing import Any
import streamlit as st
import database as db
from providers import ProviderError, cache_cover, RAWGProvider, IGDBProvider
from interfaces import MetadataProvider
from ui_helpers import cached_list_tags

def get_ordered_providers() -> list[MetadataProvider]:
    rawg_key = db.get_setting("rawg_api_key")
    igdb_id = db.get_setting("igdb_client_id")
    igdb_secret = db.get_setting("igdb_client_secret")
    
    priority = db.get_setting("provider_priority", "IGDB,RAWG").split(",")
    
    providers: list[MetadataProvider] = []
    for p in priority:
        if p.strip() == "RAWG" and rawg_key:
            providers.append(RAWGProvider(rawg_key))
        elif p.strip() == "IGDB" and igdb_id and igdb_secret:
            providers.append(IGDBProvider(igdb_id, igdb_secret))
    return providers

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
    return last_error or "No se encontraron coincidencias en ningún proveedor."

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
    status = {"Backlog": "backlog", "Played": "played", "Abandoned": "abandoned"}[destination]
    existing = {item["normalized_title"] for item in db.list_games()}
    created: list[tuple[int, str]] = []
    skipped: list[str] = []
    for title in requested:
        normalized = db.normalize_title(title)
        if normalized in existing:
            skipped.append(title)
            continue
        game_id = db.create_game(title, status=status, ready_to_play=ready if status == "backlog" else False, tag_ids=[label_to_id[name] for name in selected_tags])
        if status in {"played", "abandoned"}:
            db.change_status(game_id, status, datetime.now().year)
        existing.add(normalized)
        created.append((game_id, title))
    messages: list[str] = []
    if enrich and created:
        progress = st.progress(0, text="Buscando metadatos en proveedores…")
        for number, (game_id, title) in enumerate(created, start=1):
            messages.append(f"{title}: {enrich_one(game_id, title)}")
            progress.progress(number / len(created), text=f"Enriqueciendo {number} de {len(created)}…")
        progress.empty()
    st.success(f"Added {len(created)} game(s).")
    if skipped:
        st.info(f"Skipped duplicates: {', '.join(skipped)}")
    if messages:
        with st.expander("Enrichment Result"):
            st.write("\n\n".join(messages))