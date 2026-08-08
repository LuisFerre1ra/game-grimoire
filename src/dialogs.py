from __future__ import annotations

import html as html_mod
import json
import sqlite3
from datetime import UTC, datetime
from typing import Any

import streamlit as st

import database as db
from providers import ProviderError, map_raw_tags
from ui_helpers import (
    STATUS_LABELS,
    cached_list_tags,
    format_hours,
    queue_toast,
    readable_date,
)


def queue_dialog(kind: str, game_id: int) -> None:
    st.session_state["dialog"] = {"kind": kind, "game_id": game_id}

def dismiss_dialog() -> None:
    """Reset active dialog session state."""
    st.session_state.pop("dialog", None)

@st.dialog("Edit game", on_dismiss=dismiss_dialog)
def edit_game_dialog(game_id: int) -> None:
    item = db.get_game(game_id)
    if not item:
        st.error("Game no longer exists.")
        return
    tags = cached_list_tags()
    label_to_id = {tag["name"]: tag["id"] for tag in tags}
    selected_ids = set(db.get_game_tags(game_id))
    selected = [tag["name"] for tag in tags if tag["id"] in selected_ids]
    with st.form(f"edit_game_{game_id}"):
        title = st.text_input("Title", value=item["title"])
        ready = st.checkbox("Ready to play", value=item["ready_to_play"])
        chosen_tags = st.multiselect("Tags", list(label_to_id), default=selected)
        notes = st.text_area("Personal Notes", value=item.get("notes") or "", height=90)
        hours = st.number_input("Playtime (hours; 0 to leave undefined)", min_value=0.0, value=float(item["hours"] or 0), step=0.5)
        saved = st.form_submit_button("Save Changes", type="primary")
    if saved:
        try:
            db.update_game(
                game_id,
                title=title,
                ready_to_play=ready,
                notes=notes,
                hours=float(hours) if hours > 0 else None,
                tag_ids=[label_to_id[name] for name in chosen_tags],
            )
        except (ValueError, sqlite3.IntegrityError) as exc:
            st.error(f"Failed to save: {exc}")
            return
        queue_toast(f"'{title}' saved", icon=":material/check_circle:")
        st.session_state.pop("dialog", None)
        st.rerun()

@st.dialog("Change status", on_dismiss=dismiss_dialog)
def status_dialog(game_id: int) -> None:
    item = db.get_game(game_id)
    if not item:
        st.error("Game no longer exists.")
        return
    options = list(STATUS_LABELS)
    def format_status(val: str) -> str:
        if val == "played":
            return "Played (Finished)"
        elif val == "abandoned":
            return "Abandoned"
        return "Backlog"
    status = st.selectbox("Status", options, index=options.index(item["status"]), format_func=format_status)
    year: int | None = None
    event_notes = ""
    if status in {"played", "abandoned"}:
        st.caption("Changing status to Played or Abandoned will create a play history entry for this game.")
        year = int(st.number_input("Year Played", min_value=1900, max_value=2200, value=datetime.now(UTC).year, step=1))
        event_notes = st.text_area("Session Notes (optional)", height=80)
    if st.button("Save Status", type="primary"):
        db.change_status(game_id, status, year, event_notes)
        queue_toast(f"Status updated to {STATUS_LABELS[status]}", icon=":material/check_circle:")
        st.session_state.pop("dialog", None)
        st.rerun()

@st.dialog("Delete game", on_dismiss=dismiss_dialog)
def delete_game_dialog(game_id: int) -> None:
    item = db.get_game(game_id)
    if not item:
        st.session_state.pop("dialog", None)
        st.rerun()
        return
    st.warning(f"You are about to delete **{item['title']}** and all its history. This action cannot be undone.")
    left, right = st.columns(2)
    if left.button("Delete permanently", type="primary", use_container_width=True):
        db.delete_game(game_id)
        queue_toast(f"'{item['title']}' deleted", icon=":material/delete:")
        st.session_state.pop("dialog", None)
        st.rerun()
    if right.button("Cancel", use_container_width=True):
        st.session_state.pop("dialog", None)
        st.rerun()

@st.dialog("Clear details", on_dismiss=dismiss_dialog)
def clear_metadata_dialog(game_id: int) -> None:
    item = db.get_game(game_id)
    if not item:
        st.session_state.pop("dialog", None)
        st.rerun()
        return
    st.warning(f"All downloaded details (cover, genres, etc.) will be deleted for **{item['title']}**. The game itself stays in your library. Are you sure?")
    left, right = st.columns(2)
    if left.button("Clear details", type="primary", use_container_width=True):
        db.clear_game_metadata(game_id)
        cached_list_tags.clear()
        queue_toast(f"Details cleared for '{item['title']}'", icon=":material/delete:")
        st.session_state.pop("dialog", None)
        st.rerun()
    if right.button("Cancel", use_container_width=True):
        st.session_state.pop("dialog", None)
        st.rerun()

@st.dialog("Delete tag", on_dismiss=dismiss_dialog)
def delete_tag_dialog(tag_id: int) -> None:
    all_tags = cached_list_tags()
    tag = next((t for t in all_tags if t["id"] == tag_id), None)
    if not tag:
        st.session_state.pop("dialog", None)
        st.rerun()
        return
    st.warning(f"Are you sure you want to delete tag **{tag['name']}**? Games associated with it will lose it and this action cannot be undone.")
    left, right = st.columns(2)
    if left.button("Delete tag", type="primary", use_container_width=True):
        db.delete_tag(tag_id)
        cached_list_tags.clear()
        queue_toast(f"Tag '{tag['name']}' deleted", icon=":material/delete:")
        st.session_state.pop("dialog", None)
        st.rerun()
    if right.button("Cancel", use_container_width=True):
        st.session_state.pop("dialog", None)
        st.rerun()

@st.dialog("Restore missing tags", on_dismiss=dismiss_dialog)
def restore_missing_tags_dialog(_id: int = 0) -> None:
    st.warning("Missing default tags and provider aliases will be restored to your catalogue. Custom tags and existing games will not be modified. Are you sure?")
    left, right = st.columns(2)
    if left.button("Restore tags", type="primary", use_container_width=True):
        res = db.restore_default_tags(mode="missing")
        cached_list_tags.clear()
        st.session_state.pop("dialog", None)
        queue_toast(f"Restored {res['restored_tags']} missing tags and {res['restored_aliases']} aliases", icon=":material/restore:")
        st.rerun()
    if right.button("Cancel", use_container_width=True):
        st.session_state.pop("dialog", None)
        st.rerun()

@st.dialog("Reset default tags", on_dismiss=dismiss_dialog)
def reset_default_tags_dialog(_id: int = 0) -> None:
    st.warning("All default tags will be reset to factory settings (original categories, colors, and aliases). Custom user tags will be preserved. Are you sure?")
    left, right = st.columns(2)
    if left.button("Reset defaults", type="primary", use_container_width=True):
        db.restore_default_tags(mode="full_reset")
        cached_list_tags.clear()
        st.session_state.pop("dialog", None)
        queue_toast("Default tags reset to factory settings", icon=":material/refresh:")
        st.rerun()
    if right.button("Cancel", use_container_width=True):
        st.session_state.pop("dialog", None)
        st.rerun()

@st.dialog("Game details", on_dismiss=dismiss_dialog, width="large")
def metadata_dialog(game_id: int) -> None:
    item = db.get_game(game_id)
    if not item:
        st.error("Game no longer exists.")
        return
    st.subheader(item["title"])
    
    provider_data = db.get_game_provider_data(game_id)
    
    st.caption(f"Source: {provider_data['provider_name'] if provider_data else 'no info'}")
    
    rating_str = "—"
    playtime = format_hours(item.get("hours"))
    description = "—"

    raw_payload_meta = {}
    if provider_data:
        try:
            meta = json.loads(provider_data["raw_payload_json"])
            raw_payload_meta = meta
            if provider_data["provider_name"] == "RAWG":
                description = meta.get("description_raw") or meta.get("description") or "—"
                esrb = meta.get("esrb_rating")
                if esrb and "name" in esrb:
                    esrb["name"]
                if meta.get("rating"):
                    rating_str = f"{meta['rating']}/{meta.get('rating_top', 5)}"
            elif provider_data["provider_name"] == "IGDB":
                description = meta.get("summary") or "—"
                if meta.get("rating"):
                    rating_str = f"{meta['rating']:.1f}/100"
        except (json.JSONDecodeError, TypeError):
            pass

    status_str = "Played" if item["status"] == "played" else ("Abandoned" if item["status"] == "abandoned" else "Backlog")

    a, b, c, d = st.columns(4)
    a.metric("Status", status_str)
    b.metric("Release Date", readable_date(item.get("release_date")))
    c.metric("Duration", playtime)
    d.metric("Rating", rating_str)

    try:
        dev_info = json.loads(item.get("developer_info_json") or "{}")
        devs = ", ".join(dev_info.get("developers", [])) or "—"
        pubs = ", ".join(dev_info.get("publishers", [])) or "—"
    except (json.JSONDecodeError, TypeError):
        devs = pubs = "—"

    st.write(f"**Developers:** {devs}")
    st.write(f"**Publishers:** {pubs}")
    
    tags = db.get_game_tags_with_categories(game_id)
    
    if tags:
        for cat in dict.fromkeys(t["category"] for t in tags):
            cat_tags = [t["name"] for t in tags if t["category"] == cat]
            st.write(f"**{html_mod.escape(cat)}:** {', '.join(html_mod.escape(t) for t in cat_tags)}")
    else:
        st.write("No associated tags.")
        
    if raw_payload_meta:
        raw_tags = []
        if provider_data["provider_name"] == "RAWG":
            raw_tags.extend([g.get("name") for g in raw_payload_meta.get("genres", []) if g.get("name")])
            raw_tags.extend([t.get("name") for t in raw_payload_meta.get("tags", []) if t.get("name")])
        elif provider_data["provider_name"] == "IGDB":
            raw_tags.extend([g.get("name") for g in raw_payload_meta.get("genres", []) if g.get("name")])
            raw_tags.extend([t.get("name") for t in raw_payload_meta.get("themes", []) if t.get("name")])
            raw_tags.extend([m.get("name") for m in raw_payload_meta.get("game_modes", []) if m.get("name")])
            for mp in raw_payload_meta.get("multiplayer_modes", []):
                if mp.get("campaigncoop"): raw_tags.append("Campaign Co-op")
                if mp.get("lancoop"): raw_tags.append("LAN Co-op")
                if mp.get("offlinecoop"): raw_tags.append("Offline Co-op")
                if mp.get("onlinecoop"): raw_tags.append("Online Co-op")
                if mp.get("dropin"): raw_tags.append("Drop-in/Drop-out")
        
        if raw_tags:

            _, unmapped = map_raw_tags(raw_tags)
            if unmapped:
                st.write(f"**Other Tags (Unmapped):** {', '.join(sorted(set(unmapped)))}")
                st.caption("These tag names came from the provider but don't match any alias in your catalogue. You can add them as aliases in Settings \u2192 Tags.")
        
    st.write(f"**Description:** {description}")
    if item.get("cover_source_url"):
        st.link_button("Open source image", item["cover_source_url"])
    if provider_data and provider_data.get("raw_payload_json"):
        with st.expander("Raw provider data"):
            st.caption("The original JSON response stored from the last metadata fetch.")
            try:
                st.json(json.loads(provider_data["raw_payload_json"]))
            except (json.JSONDecodeError, TypeError):
                st.code(provider_data["raw_payload_json"], language="json")

@st.dialog("Complete information", on_dismiss=dismiss_dialog)
def enrich_game_dialog(game_id: int) -> None:
    from pages.add_games import enrich_one
    from providers import get_ordered_providers
    item = db.get_game(game_id)
    if not item:
        st.error("Game no longer exists.")
        return
    
    providers = get_ordered_providers()
    if not providers:
        st.warning("Configure credentials for a provider in Settings.")
        if st.button("Close"):
            st.session_state.pop("dialog", None)
            st.rerun()
        return

    st.write(f"Search and update details for **{item['title']}** online?")
    st.caption("Configured providers will be used in order.")
    
    left, right = st.columns(2)
    if left.button("Update data", type="primary", use_container_width=True):
        with st.spinner("Searching metadata..."):
            try:
                result = enrich_one(game_id, item['title'])
                queue_toast(result, icon=":material/cloud_done:")
            except ProviderError as exc:
                queue_toast(f"Provider error: {exc}", icon=":material/cloud_off:")
            except Exception as exc:  # noqa: BLE001
                queue_toast(f"Unexpected error: {exc}", icon=":material/error:")
        cached_list_tags.clear()
        st.session_state.pop("dialog", None)
        st.rerun()
        
    if right.button("Cancel", use_container_width=True):
        st.session_state.pop("dialog", None)
        st.rerun()

def show_pending_dialog() -> None:
    active = st.session_state.get("dialog")
    if active:
        dialogs_map = {
            "edit": edit_game_dialog,
            "status": status_dialog,
            "delete": delete_game_dialog,
            "metadata": metadata_dialog,
            "enrich": enrich_game_dialog,
            "clear_metadata": clear_metadata_dialog,
            "delete_tag": delete_tag_dialog,
            "restore_missing_tags": restore_missing_tags_dialog,
            "reset_default_tags": reset_default_tags_dialog,
        }
        handler = dialogs_map.get(active["kind"])
        if handler:
            handler(active["game_id"])

def game_actions(item: dict[str, Any], prefix: str) -> None:
    col1, col2 = st.columns([4, 1])
        
    enrich_label = "Replace information" if item.get("metadata_source") or item.get("release_date") else "Complete information"
        
    with col1:
        st.button("Details", key=f"{prefix}_details", type="primary", use_container_width=True, on_click=queue_dialog, args=("metadata", item["id"]))

    with col2:
        is_active_dialog = bool(st.session_state.get("dialog") and st.session_state["dialog"].get("game_id") == item["id"])
        popover_key = f"{prefix}_popover_{'open' if is_active_dialog else 'closed'}"
        with st.popover("⋮", help="Actions", use_container_width=True, key=popover_key):
            for kind, label in [("edit", "Edit"), ("status", "Change status"), ("enrich", enrich_label), ("clear_metadata", "Clear details"), ("delete", "Delete")]:
                st.button(label, key=f"{prefix}_{kind}", type="tertiary", use_container_width=True, on_click=queue_dialog, args=(kind, item["id"]))