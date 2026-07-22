"""Local game library application."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Iterable

import pandas as pd
import streamlit as st

import database as db
from providers import ProviderError, cache_cover, RAWGProvider, IGDBProvider
from interfaces import MetadataProvider


st.set_page_config(page_title="My Game Library", layout="wide")
db.init_database()

STATUS_LABELS = {"backlog": "Backlog", "played": "Played", "abandoned": "Abandoned"}


def inject_styles() -> None:
    st.markdown(
        """
        <style>
          .block-container { max-width: 1500px; padding-top: 1.4rem; }
          .game-placeholder {aspect-ratio: 3 / 4; width: 100%; display:flex; flex-direction:column; align-items:center;
            justify-content:center; border-radius:.55rem; color:#d7e3f5; background:linear-gradient(145deg,#24334d,#121b2b); font-size:.9rem;}
          .game-placeholder small {font-size:.78rem; margin-top:.55rem; color:#aebed2;}
          .tag-chip {display:inline-block; margin:.2rem .4rem .2rem 0; padding:.1rem .45rem; border-radius:999px;
            background:#27374d; color:#e6eefb; font-size:.78rem;}
          .muted {color:#9aa8ba; font-size:.86rem;}
          div[data-testid="stImage"] img {aspect-ratio: 3 / 4 !important; width:100% !important; height: auto !important; object-fit:cover; border-radius:.55rem;}
          div[data-testid="stFullScreenFrame"] > div > div:first-child {padding: 0.5rem; top: 0 !important;}
          div[data-testid="stPopover"] button div[data-testid="stMarkdownContainer"] {display: none;}
          button[data-testid="stPopoverButton"] > div {margin-right:0;}
          button[data-testid="stPopoverButton"] > div > div:first-child {display: none;}
          div[data-testid="stPopoverBody"] { padding: 0.25rem 0 !important; }
          div[data-testid="stPopoverBody"] .stVerticalBlock { gap: 0 !important; }
          div[data-testid="stPopoverBody"] .element-container { margin-bottom: 0 !important; }
          div[data-testid="stPopoverBody"] button { margin: 0 !important; padding: 0.35rem 1rem !important; min-height: 2.2rem !important; text-align: left !important; }
          div[data-testid="stPopoverBody"] button > div { justify-content: flex-start !important; }
          div[data-testid="stColumn"]:has(.special-tags-container) {
            position: relative;
            container-type: inline-size;
          }
          div[data-testid="stElementContainer"]:has(.special-tags-container) {
            position: absolute;
            width: calc(100% + 2px - 2rem - 20px);
            top: calc((100cqw + 2px - 2rem)*4/3);
            margin: 10px;
            transform: translateY(calc(-100% - 20px));
            z-index: 10;
          }
          /* Custom Sidebar Navigation */
          [data-testid="stSidebar"] {
            background-color: #0b1423;
            border-right: 1px solid #1a2536;
          }
          [data-testid="stSidebar"] [data-testid="stButton"] button {
            border: none;
            background-color: transparent;
            color: #8b9bb4;
            display: flex;
            justify-content: flex-start;
            padding: 0.6rem 1rem;
            border-radius: 0.4rem;
            transition: all 0.2s ease;
            box-shadow: none;
          }
          [data-testid="stSidebar"] [data-testid="stButton"] button:hover {
            background-color: #172439;
            color: #ffffff;
            transform: translateX(4px);
          }
          [data-testid="stSidebar"] [data-testid="stButton"] button[kind="primary"] {
            background-color: #1e3152;
            color: #60a5fa;
            border-left: 4px solid #3b82f6;
            border-radius: 0 0.4rem 0.4rem 0;
            font-weight: bold;
          }
          
          /* Red style for delete buttons using wrapper */
          div[data-testid="stElementContainer"]:has(.delete-btn-wrapper) {
              display: none;
          }
          div[data-testid="stElementContainer"]:has(.delete-btn-wrapper) + div[data-testid="stElementContainer"] button {
              background-color: #271216 !important;
              color: #ef4444 !important;
              border: 1px solid #6b2228 !important;
              transition: all 0.2s ease;
          }
          div[data-testid="stElementContainer"]:has(.delete-btn-wrapper) + div[data-testid="stElementContainer"] button:hover {
              background-color: #ef4444 !important;
              color: #ffffff !important;
              border: 1px solid #ef4444 !important;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


def readable_date(value: str | None) -> str:
    if not value:
        return "—"
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%d/%m/%Y")
    except ValueError:
        return value


def format_hours(value: float | None) -> str:
    return f"{value:.1f} h" if value is not None else "No duration"


def cover_reference(item: dict[str, Any]) -> str | None:
    if item.get("cover_local_path"):
        candidate = db.BASE_DIR / item["cover_local_path"]
        if candidate.exists():
            return str(candidate)
    return item.get("cover_source_url")


def tag_html(tags: Iterable[str], limit: int = 4, show_empty: bool = True) -> str:
    names = list(tags)
    shown = names[:limit]
    hidden = names[limit:]
    
    all_tags = db.list_tags()
    name_to_color = {t["name"]: t["color"] for t in all_tags}
    
    chips = []
    for name in shown:
        color = name_to_color.get(name, "#27374d")
        chips.append(f'<span class="tag-chip" style="background-color: {color}; white-space: nowrap; text-overflow: ellipsis; max-width: 150px; overflow: hidden;">{name}</span>')
        
    if hidden:
        hidden_chips = []
        for name in hidden:
            h_color = name_to_color.get(name, "#27374d")
            hidden_chips.append(f'<span class="tag-chip" style="background-color: {h_color}; margin-bottom: 0.2rem;">{name}</span>')
            
        hidden_html = "".join(hidden_chips)
        
        details_html = f'''
        <style>details > summary.overflow-chip::-webkit-details-marker {{ display: none; }}</style>
        <details style="display: inline-block; position: relative;">
            <summary class="tag-chip overflow-chip" style="background-color: #4a5568; flex-shrink: 0; cursor: pointer; list-style: none;">+{len(hidden)}</summary>
            <div style="position: absolute; bottom: 120%; right: 0; background: #0b1423; padding: 0.5rem; border: 1px solid #1a2536; border-radius: 0.4rem; z-index: 9999; display: flex; flex-wrap: wrap; width: max-content; max-width: 220px; box-shadow: 0 4px 6px rgba(0,0,0,0.5);">
                {hidden_html}
            </div>
        </details>
        '''
        chips.append(details_html)
        
    if not chips and not show_empty:
        return ""
        
    inner_html = "".join(chips) or '<span class="muted">No tags</span>'
    return f'<div style="display: flex; flex-wrap: nowrap; align-items: center; width: 100%;">{inner_html}</div>'


def queue_dialog(kind: str, game_id: int) -> None:
    st.session_state["dialog"] = {"kind": kind, "game_id": game_id}


def dismiss_dialog() -> None:
    """Clear the server-side dialog state when the user clicks its X button."""
    st.session_state.pop("dialog", None)


@st.dialog("Edit game", on_dismiss=dismiss_dialog)
def edit_game_dialog(game_id: int) -> None:
    item = db.get_game(game_id)
    if not item:
        st.error("Game no longer exists.")
        return
    tags = db.list_tags()
    custom_tags = [t for t in tags if t["is_custom"]]
    label_to_id = {tag["name"]: tag["id"] for tag in custom_tags}
    selected_ids = set(db.get_game_tags(game_id))
    selected = [tag["name"] for tag in custom_tags if tag["id"] in selected_ids]
    with st.form(f"edit_game_{game_id}"):
        title = st.text_input("Title", value=item["title"])
        ready = st.checkbox("Ready to play", value=item["ready_to_play"])
        chosen_tags = st.multiselect("Personal Tags", list(label_to_id), default=selected)
        notes = st.text_area("Personal Notes", value=item.get("notes") or "", height=90)
        hours = st.number_input("Playtime (hours; 0 to leave undefined)", min_value=0.0, value=float(item["hours"] or 0), step=0.5)
        saved = st.form_submit_button("Save Changes", type="primary")
    if saved:
        try:
            db.update_game(game_id, title=title, ready_to_play=ready, notes=notes, tag_ids=[label_to_id[name] for name in chosen_tags])
            if hours > 0:
                db.add_or_select_estimate(game_id, float(hours), source="Manual")
            else:
                db.clear_selected_estimate(game_id)
        except Exception as exc:
            st.error(f"Failed to save: {exc}")
            return
        st.session_state.pop("dialog", None)
        st.rerun()


@st.dialog("Cambiar status", on_dismiss=dismiss_dialog)
def status_dialog(game_id: int) -> None:
    item = db.get_game(game_id)
    if not item:
        st.error("Game no longer exists.")
        return
    options = list(STATUS_LABELS)
    status = st.selectbox("Status", options, index=options.index(item["status"]), format_func=lambda value: STATUS_LABELS[value])
    year: int | None = None
    event_notes = ""
    if status in {"played", "abandoned"}:
        year = int(st.number_input("Year Played", min_value=1900, max_value=2200, value=datetime.now().year, step=1))
        event_notes = st.text_area("Session Notes (optional)", height=80)
    if st.button("Save Status", type="primary"):
        db.change_status(game_id, status, year, event_notes)
        st.session_state.pop("dialog", None)
        st.rerun()


@st.dialog("Delete game", on_dismiss=dismiss_dialog)
def delete_game_dialog(game_id: int) -> None:
    item = db.get_game(game_id)
    if not item:
        st.session_state.pop("dialog", None)
        st.rerun()
    st.warning(f"You are about to delete **{item['title']}** and all its history. This action cannot be undone.")
    left, right = st.columns(2)
    if left.button("Delete definitivamente", type="primary"):
        db.delete_game(game_id)
        st.session_state.pop("dialog", None)
        st.rerun()
    if right.button("Cancel"):
        st.session_state.pop("dialog", None)
        st.rerun()

@st.dialog("Limpiar details", on_dismiss=dismiss_dialog)
def clear_metadata_dialog(game_id: int) -> None:
    item = db.get_game(game_id)
    if not item:
        st.session_state.pop("dialog", None)
        st.rerun()
    st.warning(f"All downloaded details (cover, genres, etc.) will be deleted for **{item['title']}**. Are you sure?")
    left, right = st.columns(2)
    if left.button("Limpiar details", type="primary"):
        db.clear_game_metadata(game_id)
        st.session_state.pop("dialog", None)
        st.rerun()
    if right.button("Cancel"):
        st.session_state.pop("dialog", None)
        st.rerun()


@st.dialog("Delete tag", on_dismiss=dismiss_dialog)
def delete_tag_dialog(tag_id: int) -> None:
    all_tags = db.list_tags()
    tag = next((t for t in all_tags if t["id"] == tag_id), None)
    if not tag:
        st.session_state.pop("dialog", None)
        st.rerun()
    st.warning(f"Are you sure you want to delete tag **{tag['name']}**? Games associated with it will lose it and this action cannot be undone.")
    left, right = st.columns(2)
    if left.button("Delete tag", type="primary", use_container_width=True):
        db.delete_tag(tag_id)
        st.session_state.pop("dialog", None)
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
    
    provider_data = None
    with db.connection() as conn:
        provider_data = conn.execute("SELECT provider_name, raw_payload_json FROM game_provider_data WHERE game_id = ? ORDER BY fetched_at DESC LIMIT 1", (game_id,)).fetchone()
    
    st.caption(f"Source: {provider_data['provider_name'] if provider_data else 'no info'}")
    
    rating_str = "—"
    playtime = format_hours(item.get("hours"))
    age_rating = "—"
    description = "—"

    if provider_data:
        try:
            meta = json.loads(provider_data["raw_payload_json"])
            if provider_data["provider_name"] == "RAWG":
                description = meta.get("description_raw") or meta.get("description") or "—"
                esrb = meta.get("esrb_rating")
                if esrb and "name" in esrb:
                    age_rating = esrb["name"]
                if meta.get("rating"):
                    rating_str = f"{meta['rating']}/{meta.get('rating_top', 5)}"
            elif provider_data["provider_name"] == "IGDB":
                description = meta.get("summary") or "—"
                if meta.get("rating"):
                    rating_str = f"{meta['rating']:.1f}/100"
        except json.JSONDecodeError:
            pass

    a, b, c = st.columns(3)
    a.metric("Lanzamiento", readable_date(item.get("release_date")))
    b.metric("Duration", playtime)
    c.metric("Valoración", rating_str)

    try:
        dev_info = json.loads(item.get("developer_info_json") or "{}")
        devs = ", ".join(dev_info.get("developers", [])) or "—"
        pubs = ", ".join(dev_info.get("publishers", [])) or "—"
    except json.JSONDecodeError:
        devs = pubs = "—"

    st.write(f"**Developers:** {devs}")
    st.write(f"**Publishers:** {pubs}")
    
    with db.connection() as conn:
        tags = conn.execute("SELECT t.name, t.category FROM tags t JOIN game_tags gt ON t.id = gt.tag_id WHERE gt.game_id = ? ORDER BY t.category, t.name", (game_id,)).fetchall()
    
    if tags:
        for cat in set(t["category"] for t in tags):
            cat_tags = [t["name"] for t in tags if t["category"] == cat]
            st.write(f"**{cat}:** {', '.join(cat_tags)}")
    else:
        st.write("No associated tags.")
        
    st.write(f"**Description:** {description}")
    if item.get("cover_source_url"):
        st.link_button("Abrir imagen de origen", item["cover_source_url"])
    if provider_data:
        with st.expander("Internal Archive"):
            st.json(json.loads(provider_data["raw_payload_json"]))


@st.dialog("Completar información", on_dismiss=dismiss_dialog)
def enrich_game_dialog(game_id: int) -> None:
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
    if left.button("Update data", type="primary"):
        with st.spinner("Buscando metadatos..."):
            try:
                result = enrich_one(game_id, item['title'])
                st.toast(result)
            except Exception as exc:
                st.toast(f"Error inesperado: {exc}")
        st.session_state.pop("dialog", None)
        st.rerun()
        
    if right.button("Cancel"):
        st.session_state.pop("dialog", None)
        st.rerun()


def show_pending_dialog() -> None:
    active = st.session_state.get("dialog")
    if active:
        {"edit": edit_game_dialog, "status": status_dialog, "delete": delete_game_dialog, "metadata": metadata_dialog, "enrich": enrich_game_dialog, "clear_metadata": clear_metadata_dialog, "delete_tag": delete_tag_dialog}[active["kind"]](active["game_id"])


def game_actions(item: dict[str, Any], prefix: str) -> None:
    col1, col2 = st.columns([4, 1])
        
    enrich_label = "Reemplazar información" if item.get("metadata_source") or item.get("release_date") else "Completar información"
        
    with col1:
        st.button("Details", key=f"{prefix}_details", type="primary", use_container_width=True, on_click=queue_dialog, args=("metadata", item["id"]))

    with col2:
        is_active_dialog = st.session_state.get("dialog") and st.session_state["dialog"]["game_id"] == item["id"]
        popover_key = f"{prefix}_popover_{'open' if is_active_dialog else 'closed'}"
        with st.popover("⋮", help="Actions", use_container_width=True, key=popover_key):
            for kind, label in [("edit", "Edit"), ("status", "Change status"), ("enrich", enrich_label), ("clear_metadata", "Limpiar details"), ("delete", "Delete")]:
                st.button(label, key=f"{prefix}_{kind}", type="tertiary", use_container_width=True, on_click=queue_dialog, args=(kind, item["id"]))


def render_card(item: dict[str, Any], prefix: str) -> None:
    with st.container(border=True):
        cover = cover_reference(item)
        if cover:
            st.image(cover, width="stretch")
        else:
            st.markdown('<div class="game-placeholder">Sin cover</div>', unsafe_allow_html=True)
            st.markdown("<div style='margin-top: 0.5rem;'></div>", unsafe_allow_html=True)
            
        all_tags = db.list_tags()
        main_tags_names = {t["name"] for t in all_tags if t.get("is_main")}
        special_tags = [t for t in item["tags"] if t in main_tags_names]
        normal_tags = [t for t in item["tags"] if t not in main_tags_names]
        
        if special_tags:
            st.markdown(f"<div class='special-tags-container'>{tag_html(special_tags, limit=10, show_empty=False)}</div>", unsafe_allow_html=True)
            
        safe_title = item["title"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
        title_html = f'<div title="{safe_title}" style="display: -webkit-box; -webkit-line-clamp: 1; -webkit-box-orient: vertical; overflow: hidden; font-weight: bold; line-height: 1.4; height: 1.4em; margin-bottom: 0.5rem;">{safe_title}</div>'
        st.markdown(title_html, unsafe_allow_html=True)
        
        detail = format_hours(item.get("hours"))
        if item["status"] == "backlog" and item["ready_to_play"]:
            detail += " · Ready to play"
        st.markdown(f"<div style='font-size: 0.86rem; color: #9aa8ba; margin-bottom: 0.3rem;'>{detail}</div>", unsafe_allow_html=True)
        st.markdown(tag_html(normal_tags, limit=2) + "<div style='margin-bottom: 0.6rem;'></div>", unsafe_allow_html=True)
        game_actions(item, prefix)


def filter_and_sort(items: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    tags = db.list_tags()
    with st.container(border=True):
        row1_col1, row1_col2, row1_col3 = st.columns([2, 1, 1], vertical_alignment="bottom")
        query = row1_col1.text_input("Search by title", key=f"{key}_search")
        wanted_tags = row1_col2.multiselect("Tags (incluir)", [tag["name"] for tag in tags], key=f"{key}_tags")
        excluded_tags = row1_col3.multiselect("Tags (excluir)", [tag["name"] for tag in tags], key=f"{key}_tags_exc")
        
        row2_col1, row2_col2, row2_col3 = st.columns([2, 1, 1], vertical_alignment="bottom")
        with row2_col1:
            duration_category = st.radio("Duration", ["Todas", "Cortos (<10h)", "Medios (10-30h)", "Largos (+30h)"], horizontal=True, key=f"{key}_duration")
        
        only_ready = row2_col2.checkbox("Solo listos para jugar", key=f"{key}_ready", disabled=key != "backlog")
        include_unknown = row2_col3.checkbox("Include without duration", value=True, key=f"{key}_unknown")

        sort_col, direction, view_col = st.columns([2, 1, 1], vertical_alignment="bottom")
        sort_label = sort_col.selectbox("Sort by", ["Title", "Hours", "Date added", "Date de lanzamiento"], key=f"{key}_sort")
        descending = direction.toggle("Descendente", key=f"{key}_descending")
        view = view_col.radio("View", ["Cards", "Table"], horizontal=True, key=f"{key}_view")

    def match_duration(hours: float | None) -> bool:
        if duration_category == "Todas": return True
        if hours is None: return True
        h = float(hours)
        if duration_category == "Cortos (<10h)" and h < 10: return True
        if duration_category == "Medios (10-30h)" and 10 <= h < 30: return True
        if duration_category == "Largos (+30h)" and h >= 30: return True
        return False

    text = query.strip().casefold()
    filtered = [
        item for item in items
        if (not text or text in item["title"].casefold())
        and (not wanted_tags or set(wanted_tags).issubset(item["tags"]))
        and (not excluded_tags or not set(excluded_tags).intersection(item["tags"]))
        and (not only_ready or item["ready_to_play"])
        and (include_unknown or item["hours"] is not None)
        and match_duration(item["hours"])
    ]
    fields = {"Title": "title", "Hours": "hours", "Date added": "added_at", "Date de lanzamiento": "release_date"}
    field = fields[sort_label]
    present = [item for item in filtered if item.get(field) is not None]
    missing = [item for item in filtered if item.get(field) is None]
    present.sort(key=lambda item: item["title"].casefold() if field == "title" else item[field], reverse=descending)
    st.session_state[f"{key}_active_view"] = view
    return present + missing


def render_cards(items: list[dict[str, Any]], key: str) -> None:
    page_size = st.select_slider("Games por página", options=[12, 24, 36, 48], value=24, key=f"{key}_page_size")
    pages = max(1, (len(items) + page_size - 1) // page_size)
    
    page_state_key = f"{key}_page_state"
    if page_state_key not in st.session_state:
        st.session_state[page_state_key] = 1
        
    if st.session_state[page_state_key] > pages:
        st.session_state[page_state_key] = max(1, pages)
        
    page = st.session_state[page_state_key]
    
    def render_pagination(suffix: str) -> None:
        col1, col2, col3 = st.columns([1, 8, 1])
        if col1.button("<", key=f"{key}_prev_{suffix}", disabled=page <= 1, use_container_width=True):
            st.session_state[page_state_key] -= 1
            st.rerun()
        col2.markdown(f"<div style='text-align: center; padding-top: 0.5rem;'><b>Página {page} de {pages}</b></div>", unsafe_allow_html=True)
        if col3.button(">", key=f"{key}_next_{suffix}", disabled=page >= pages, use_container_width=True):
            st.session_state[page_state_key] += 1
            st.rerun()

    render_pagination("top")
        
    current = items[(page - 1) * page_size : page * page_size]
    st.caption(f"Mostrando {len(current)} de {len(items)} games")
    for start in range(0, len(current), 4):
        columns = st.columns(4)
        for column, item in zip(columns, current[start : start + 4]):
            with column:
                render_card(item, f"{key}_{item['id']}")
                
    render_pagination("bottom")


def render_table(items: list[dict[str, Any]], key: str) -> None:
    rows = [{
        "Title": item["title"], "Hours": item["hours"], "Ready": "Sí" if item["ready_to_play"] else "—",
        "Tags": ", ".join(item["tags"]), "Lanzamiento": readable_date(item.get("release_date")),
        "Added": readable_date(item.get("added_at")), "Años played": ", ".join(map(str, sorted(set(item["years"])))),
    } for item in items]
    event = st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row", key=f"{key}_table", column_config={"Hours": st.column_config.NumberColumn(format="%.1f h")})
    selected_rows = event.selection.rows if event and event.selection.rows else []
    if selected_rows:
        chosen = items[selected_rows[0]]
        left, right = st.columns([5, 1])
        left.info(f"Seleccionado: **{chosen['title']}**")
        with right:
            game_actions(chosen, f"{key}_table_{chosen['id']}")
    else:
        st.caption("Selecciona una fila para abrir sus acciones.")


def inventory_page(title: str, statuses: list[str], key: str) -> None:
    st.title(title)
    items = db.list_games(statuses)
    if key in ("backlog", "played"):
        known = [float(item["hours"]) for item in items if item.get("hours") is not None]
        missing = len(items) - len(known)
        known_sum = sum(known)
        predicted_total: float | None = None
        margin: float | None = None
        
        if missing and len(known) > 1:
            mean = known_sum / len(known)
            variance = sum((value - mean) ** 2 for value in known) / (len(known) - 1)
            std_dev = variance ** 0.5
            predicted_total = known_sum + missing * mean
            margin = 1.28 * std_dev * (missing + (missing**2 / len(known))) ** 0.5
        elif not missing:
            predicted_total = known_sum
            margin = 0

        a, b, c = st.columns(3)
        a.metric("Games", len(items))
        b.metric("Known hours", f"{known_sum:.1f} h")
        c.metric("Predicted hours", "—" if predicted_total is None else f"{predicted_total:.1f} h")
        if margin is not None:
            st.caption(f"80% estimate: ± {margin:.1f} h · {missing} without duration.")
    if not items:
        st.info("Todavía no hay games aquí. Añade títulos desde «Add Games».")
        return
    shown = filter_and_sort(items, key)
    st.caption(f"{len(shown)} game(s) match filters.")
    if st.session_state.get(f"{key}_active_view", "Tarjetas") == "Tarjetas":
        render_cards(shown, key)
    else:
        render_table(shown, key)


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
    tags = db.list_tags()
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


def configuration_page() -> None:
    st.title("Settings")
    connection_tab, tags_tab, enrichment_tab, export_tab = st.tabs(["Connections", "Tags", "Enrichment"ualizar catálogo", "Exportar"])
    with connection_tab:
        st.subheader("Servicios optionales")
        st.caption("The application works without external services; los proveedores se consultan sólo al pedirlo.")
        with st.form("connections"):
            current_val = db.get_setting("provider_priority", "IGDB,RAWG")
            default_selection = [p for p in current_val.split(",") if p in ["IGDB", "RAWG"]]
            
            provider_order_list = st.multiselect(
                "Orden de prioridad de proveedores (selecciona en orden de preferencia)", 
                options=["IGDB", "RAWG"], 
                default=default_selection
            )
            rawg_key = st.text_input("Key de API de RAWG", value=db.get_setting("rawg_api_key"), type="password")
            igdb_id = st.text_input("Client ID de IGDB", value=db.get_setting("igdb_client_id"))
            igdb_secret = st.text_input("Client Secret de IGDB", value=db.get_setting("igdb_client_secret"), type="password")
            saved = st.form_submit_button("Save configuration")
        if saved:
            db.set_setting("provider_priority", ",".join(provider_order_list))
            db.set_setting("rawg_api_key", rawg_key.strip())
            db.set_setting("igdb_client_id", igdb_id.strip())
            db.set_setting("igdb_client_secret", igdb_secret.strip())
            st.success("Settings guardada localmente.")
    with tags_tab:
        st.subheader("Catálogo de tags")
        
        all_tags = db.list_tags()
        existing_cats = sorted(list(set(t["category"] for t in all_tags if t.get("category"))))
        if not existing_cats:
            existing_cats = ["Status", "Reviews", "Mode", "Requirement", "Compatibility", "Other"]
        cat_options = existing_cats + ["+ New category..."]
        
        if st.button("+ Add new tag", type="primary"):
            try:
                import time
                db.add_tag(f"New tag {int(time.time() * 1000) % 10000}", "Other", "#7E8996", False)
                st.rerun()
            except Exception as exc:
                st.error(f"Error al create: {exc}")
                
        all_tags = db.list_tags()
        
        if "tag_order" not in st.session_state:
            st.session_state["tag_order"] = [t["id"] for t in all_tags]
            
        known_ids = set(st.session_state["tag_order"])
        new_order = list(st.session_state["tag_order"])
        
        # Enforce that newly created tags are pushed to the absolute top of the order
        for t in all_tags:
            if t["id"] not in known_ids:
                new_order.insert(0, t["id"])
                known_ids.add(t["id"])
                
        # Force Streamlit to recognize the state mutation
        st.session_state["tag_order"] = new_order
        
        order_map = {tid: i for i, tid in enumerate(st.session_state["tag_order"])}
        all_tags.sort(key=lambda t: order_map.get(t["id"], 999999))
        if all_tags:
            h1, h2, h3, h4, h5 = st.columns([4, 4, 0.6, 0.8, 1.1])
            h1.markdown("**Name**")
            h2.markdown("**Category**")
            h3.markdown("**Color**")
            h4.markdown("<div style='text-align: center; font-weight: bold;'>Principal</div>", unsafe_allow_html=True)
            h5.markdown("<div style='text-align: center; font-weight: bold;'>Acción</div>", unsafe_allow_html=True)
            
            for tag in all_tags:
                c1, c2, c3, c4, c5 = st.columns([4, 4, 0.6, 0.8, 1.1])
                t_id = tag["id"]
                new_name = c1.text_input("Name", value=tag["name"], key=f"t_name_{t_id}", label_visibility="collapsed")
                
                current_cat = tag["category"]
                cat_idx = cat_options.index(current_cat) if current_cat in cat_options else 0
                cat_val = c2.selectbox("Category", cat_options, index=cat_idx, key=f"t_cat_sel_{t_id}", label_visibility="collapsed")
                if cat_val == "+ New category...":
                    new_cat = c2.text_input("New category", value="", key=f"t_cat_new_{t_id}", label_visibility="collapsed", placeholder="Escribe aquí...")
                else:
                    new_cat = cat_val
                
                effective_cat = tag["category"] if (cat_val == "+ New category..." and not new_cat.strip()) else new_cat.strip()
                
                new_color = c3.color_picker("Color", value=tag["color"], key=f"t_col_{t_id}", label_visibility="collapsed")
                
                with c4:
                    _, c_chk, _ = st.columns([1, 1.5, 1])
                    new_main = c_chk.checkbox("Sí", value=bool(tag.get("is_main", 0)), key=f"t_main_{t_id}", label_visibility="collapsed")
                
                with c5:
                    st.markdown('<div class="delete-btn-wrapper"></div>', unsafe_allow_html=True)
                    if st.button("Delete", key=f"del_{t_id}", type="secondary", use_container_width=True):
                        queue_dialog("delete_tag", t_id)
                
                changed = (new_name != tag["name"] or effective_cat != tag["category"] or new_color != tag["color"] or new_main != bool(tag.get("is_main", 0)))
                
                if changed:
                    try:
                        db.update_tag(t_id, new_name, effective_cat, new_color, new_main)
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))
    with enrichment_tab:
        st.subheader("Update missing data")
        games = db.list_games()
        if not get_ordered_providers():
            st.info("Configure a provider first (IGDB or RAWG) in Connections.")
        elif not games:
            st.info("No games to update.")
        else:
            # Re-check what counts as missing info. In this new architecture, if they aren't in game_provider_data
            missing_info = []
            with db.connection() as conn:
                for g in games:
                    prov = conn.execute("SELECT 1 FROM game_provider_data WHERE game_id = ?", (g["id"],)).fetchone()
                    if not prov:
                        missing_info.append(g)
            
            c1, c2 = st.columns(2)
            c1.metric("Games in library", len(games))
            c2.metric("Games no info", len(missing_info))
            
            st.write("### Opciones de actualización")
            st.write("**Option A: Search missing data**\nBusca details y covers únicamente para los games que aún no tienen información.")
            btn_missing = st.button("Search missing data", disabled=len(missing_info) == 0, type="primary")
            
            st.write("**Opción B: Actualización completa**\nVuelve a descargar la información de todos tus games. Útil si quieres refrescar las valoraciones o covers.")
            btn_all = st.button("Update whole collection")
            
            to_update = []
            if btn_missing:
                to_update = missing_info
            elif btn_all:
                to_update = games
                
            if to_update:
                progress = st.progress(0, text="Actualizando datos…")
                results: list[str] = []
                for number, item in enumerate(to_update, start=1):
                    try:
                        results.append(f"{item['title']}: {enrich_one(item['id'], item['title'])}")
                    except ProviderError as exc:
                        results.append(f"{item['title']}: {exc}")
                    progress.progress(number / len(to_update), text=f"Actualizando {number} de {len(to_update)}…")
                progress.empty()
                st.success("Proceso terminado.")
                with st.expander("Ver resultados detallados"):
                    st.write("\n\n".join(results))
    with export_tab:
        st.subheader("Exportaciones locales")
        rows = db.export_rows()
        frame = pd.DataFrame(rows)
        st.download_button("Descargar CSV", frame.to_csv(index=False).encode("utf-8-sig"), "library_games.csv", "text/csv")
        st.download_button("Descargar JSON", json.dumps(rows, ensure_ascii=False, indent=2).encode("utf-8"), "library_games.json", "application/json")
        if db.DB_PATH.exists():
            st.download_button("Descargar base SQLite", db.DB_PATH.read_bytes(), "game_library.db", "application/octet-stream")


def main() -> None:
    inject_styles()
    pages = ["Backlog", "Played", "Add Games", "Settings"]
    if "page" not in st.session_state:
        st.session_state["page"] = "Backlog"
        
    page = st.session_state["page"]
    with st.sidebar:
        st.markdown("<h2 style='text-align: center; margin-bottom: 2rem; color: #e6eefb; font-weight: 700; letter-spacing: 0.5px;'>Library</h2>", unsafe_allow_html=True)
        for p in pages:
            if st.button(p, key=f"nav_{p}", use_container_width=True, type="primary" if page == p else "secondary"):
                if p != "Settings" and "tag_order" in st.session_state:
                    del st.session_state["tag_order"]
                st.session_state["page"] = p
                st.rerun()
    if page == "Backlog": inventory_page("Backlog", ["backlog"], "backlog")
    elif page == "Played": inventory_page("Played & Abandoned", ["played", "abandoned"], "played")
    elif page ==: statistics_page()
    elif page == "Add Games": add_games_page()
    elif page == "Settings": configuration_page()
    show_pending_dialog()


if __name__ == "__main__":
    main()
