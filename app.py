"""Local game library application."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Iterable

import pandas as pd
import streamlit as st

import database as db
from providers import ProviderError, cache_cover, fetch_rawg_metadata


st.set_page_config(page_title="My Game Library", layout="wide")
db.init_database()

STATUS_LABELS = {"backlog": "Backlog", "played": "Played", "abandoned": "Abandoned"}


def inject_styles() -> None:
    st.markdown(
        """
        <style>
          .block-container { max-width: 1500px; padding-top: 1.4rem; }
          .game-placeholder {height:168px; display:flex; flex-direction:column; align-items:center;
            justify-content:center; border-radius:.55rem; color:#d7e3f5; background:linear-gradient(145deg,#24334d,#121b2b); font-size:.9rem;}
          .game-placeholder small {font-size:.78rem; margin-top:.55rem; color:#aebed2;}
          .tag-chip {display:inline-block; margin:.2rem .4rem .2rem 0; padding:.1rem .45rem; border-radius:999px;
            background:#27374d; color:#e6eefb; font-size:.78rem;}
          .muted {color:#9aa8ba; font-size:.86rem;}
          div[data-testid="stImage"] img {height:168px !important; width:100% !important; object-fit:cover; border-radius:.55rem;}
          div[data-testid="stFullScreenFrame"] > div > div:first-child {padding: 0.5rem; top: 0 !important;}
          div[data-testid="stPopover"] button div[data-testid="stMarkdownContainer"] {display: none;}
          button[data-testid="stPopoverButton"] > div {margin-right:0;}
          button[data-testid="stPopoverButton"] > div > div:first-child {display: none;}
          div[data-testid="stPopoverBody"] { padding: 0.25rem 0 !important; }
          div[data-testid="stPopoverBody"] .stVerticalBlock { gap: 0 !important; }
          div[data-testid="stPopoverBody"] .element-container { margin-bottom: 0 !important; }
          div[data-testid="stPopoverBody"] button { margin: 0 !important; padding: 0.35rem 1rem !important; min-height: 2.2rem !important; text-align: left !important; }
          div[data-testid="stPopoverBody"] button > div { justify-content: flex-start !important; }
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


def tag_html(tags: Iterable[str], limit: int = 4) -> str:
    names = list(tags)
    shown = names[:limit] + ([f"+{len(names) - limit}"] if len(names) > limit else [])
    
    all_tags = db.list_tags()
    name_to_color = {t["name"]: t["color"] for t in all_tags}
    
    chips = []
    for name in shown:
        color = name_to_color.get(name, "#27374d")
        chips.append(f'<span class="tag-chip" style="background-color: {color};">{name}</span>')
        
    return "".join(chips) or '<span class="muted">No tags</span>'


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
    label_to_id = {tag["name"]: tag["id"] for tag in tags}
    selected_ids = set(db.get_game_tags(game_id))
    selected = [tag["name"] for tag in tags if tag["id"] in selected_ids]
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


@st.dialog("Game details", on_dismiss=dismiss_dialog, width="large")
def metadata_dialog(game_id: int) -> None:
    item = db.get_game(game_id)
    if not item:
        st.error("Game no longer exists.")
        return
    st.subheader(item["title"])
    st.caption(f"Source: {item.get('metadata_source') or 'no info'}")
    
    meta = {}
    rating_str = "—"
    metacritic = "—"
    playtime = "—"
    age_rating = "—"
    publishers_str = "—"
    description = "—"

    if item.get("external_metadata_json"):
        try:
            meta = json.loads(item["external_metadata_json"])
            if "rating" in meta and "rating_top" in meta and meta["rating"] > 0:
                rating_str = f"{meta['rating']}/{meta['rating_top']}"
            
            if meta.get("metacritic"):
                metacritic = str(meta["metacritic"])
            
            if meta.get("playtime"):
                playtime = f"{meta['playtime']} h"
                
            esrb = meta.get("esrb_rating")
            if esrb and "name" in esrb:
                age_rating = esrb["name"]
                
            pubs = meta.get("publishers", [])
            if pubs:
                publishers_str = ", ".join(p["name"] for p in pubs)
                
            description = meta.get("description_raw") or meta.get("description") or "—"
        except json.JSONDecodeError:
            pass

    a, b, c = st.columns(3)
    a.metric("Lanzamiento", readable_date(item.get("release_date")))
    b.metric("Duration", format_hours(item.get("hours")))
    c.metric("Valoración", rating_str)
    
    d, e, f = st.columns(3)
    d.metric("Metacritic", metacritic)
    e.metric("Tiempo RAWG", playtime)
    f.metric("Clasificación", age_rating)

    def field_list(name: str) -> str:
        try:
            return ", ".join(json.loads(item.get(name) or "[]")) or "—"
        except json.JSONDecodeError:
            return "—"

    st.write(f"**Developers:** {field_list('developers_json')}")
    st.write(f"**Publishers:** {publishers_str}")
    st.write(f"**Géneros:** {field_list('genres_json')}")
    st.write(f"**Tags:** {field_list('rawg_tags_json')}")
    st.write(f"**Description:** {description}")
    if item.get("cover_source_url"):
        st.link_button("Abrir imagen de origen", item["cover_source_url"])
    if item.get("external_metadata_json"):
        with st.expander("Internal Archive"):
            st.json(json.loads(item["external_metadata_json"]))


@st.dialog("Completar información", on_dismiss=dismiss_dialog)
def enrich_game_dialog(game_id: int) -> None:
    item = db.get_game(game_id)
    if not item:
        st.error("Game no longer exists.")
        return
    
    if not db.get_setting("rawg_api_key"):
        st.warning("Configura primero la key de RAWG en Settings.")
        if st.button("Close"):
            st.session_state.pop("dialog", None)
            st.rerun()
        return

    st.write(f"Search and update details for **{item['title']}** online?")
    
    left, right = st.columns(2)
    if left.button("Update data", type="primary"):
        with st.spinner("Buscando en RAWG..."):
            try:
                result = enrich_one(game_id, item['title'])
                st.toast(result)
            except ProviderError as exc:
                st.toast(f"Error: {exc}")
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
        {"edit": edit_game_dialog, "status": status_dialog, "delete": delete_game_dialog, "metadata": metadata_dialog, "enrich": enrich_game_dialog, "clear_metadata": clear_metadata_dialog}[active["kind"]](active["game_id"])


def game_actions(item: dict[str, Any], prefix: str) -> None:
    if st.session_state.get("dialog"):
        st.button("", help="Actions", disabled=True, use_container_width=True, key=f"{prefix}_disabled")
        return
        
    with st.popover("", help="Actions", use_container_width=True):
        for kind, label in [("edit", "Edit"), ("status", "Change status"), ("metadata", "Ver details"), ("enrich", "Completar información"), ("clear_metadata", "Limpiar details"), ("delete", "Delete")]:
            if st.button(label, key=f"{prefix}_{kind}", type="tertiary", use_container_width=True):
                queue_dialog(kind, item["id"])
                st.rerun()


def render_card(item: dict[str, Any], prefix: str) -> None:
    with st.container(height=355, border=True):
        cover = cover_reference(item)
        if cover:
            st.image(cover, width="stretch")
        else:
            st.markdown('<div class="game-placeholder">Sin cover</div>', unsafe_allow_html=True)
            st.markdown("<div style='margin-top: 0.5rem;'></div>", unsafe_allow_html=True)
        left, right = st.columns([5, 2])
        safe_title = item["title"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
        title_html = f'<div title="{safe_title}" style="display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; font-weight: bold; line-height: 1.4; max-height: 2.8em; margin-bottom: 0.5rem;">{safe_title}</div>'
        left.markdown(title_html, unsafe_allow_html=True)
        with right:
            game_actions(item, prefix)
        detail = format_hours(item.get("hours"))
        if item["status"] == "backlog" and item["ready_to_play"]:
            detail += " · Ready to play"
        st.caption(detail)
        st.markdown(tag_html(item["tags"]), unsafe_allow_html=True)


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


def enrich_one(game_id: int, title: str) -> str:
    metadata, message = fetch_rawg_metadata(title, db.get_setting("rawg_api_key"))
    if not metadata:
        return message or "No se encontraron metadatos."
    try:
        local_cover = cache_cover(metadata.get("background_image"), game_id)
    except Exception:
        local_cover = None
    db.update_game_metadata(game_id, metadata, local_cover)
    return message or "Metadatos actualizados."


def add_games_page() -> None:
    st.title("Add Games")
    st.write("Paste one title per line. Duplicates are detected by normalized title.")
    tags = db.list_tags()
    label_to_id = {tag["name"]: tag["id"] for tag in tags}
    has_rawg = bool(db.get_setting("rawg_api_key"))
    with st.form("add_games"):
        titles = st.text_area("Titles", height=220, placeholder="Hades\nOuter Wilds\nBalatro")
        destination = st.radio("Add to", ["Backlog", "Played", "Abandoned"], horizontal=True)
        selected_tags = st.multiselect("Initial Tags", list(label_to_id))
        ready = st.checkbox("Mark as ready to play", disabled=destination != "Backlog")
        enrich = st.checkbox("Fetch details and cover automatically", value=has_rawg, disabled=not has_rawg)
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
        progress = st.progress(0, text="Buscando metadatos en RAWG…")
        for number, (game_id, title) in enumerate(created, start=1):
            try:
                messages.append(f"{title}: {enrich_one(game_id, title)}")
            except ProviderError as exc:
                messages.append(f"{title}: {exc}")
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
        st.caption("The application works without external services; RAWG se consulta sólo al pedirlo.")
        with st.form("connections"):
            rawg_key = st.text_input("Key de API de RAWG", value=db.get_setting("rawg_api_key"), type="password")
            saved = st.form_submit_button("Save configuration")
        if saved:
            db.set_setting("rawg_api_key", rawg_key.strip())
            st.success("Settings guardada localmente.")
    with tags_tab:
        st.subheader("Catálogo de tags personales")
        with st.form("new_tag", clear_on_submit=True):
            one, two, three = st.columns([2, 2, 1])
            name = one.text_input("Name")
            category = two.selectbox("Category", ["Status", "Reviews", "Mode", "Requirement", "Compatibility", "Other"])
            color = three.color_picker("Color", "#7E8996")
            added = st.form_submit_button("Create tag")
        if added:
            try:
                db.add_tag(name, category, color); st.success("Tag created."); st.rerun()
            except Exception as exc:
                st.error(f"Could not create: {exc}")
        all_tags = db.list_tags()
        if all_tags:
            choices = {f"{tag['name']} · {tag['category']}": tag for tag in all_tags}
            selected = choices[st.selectbox("Edit tag", list(choices))]
            with st.form("edit_tag"):
                name = st.text_input("Tag name", selected["name"])
                category = st.text_input("Category", selected["category"])
                color = st.color_picker("Color", selected["color"])
                save_tag, remove_tag = st.columns(2)
                save_clicked = save_tag.form_submit_button("Save tag")
                delete_clicked = remove_tag.form_submit_button("Delete tag")
            try:
                if save_clicked:
                    db.update_tag(selected["id"], name, category, color); st.success("Tag updated."); st.rerun()
                if delete_clicked:
                    db.delete_tag(selected["id"]); st.success("Tag deleted."); st.rerun()
            except Exception as exc:
                st.error(f"Could not modify tag: {exc}")
    with enrichment_tab:
        st.subheader("Update missing data")
        games = db.list_games()
        if not db.get_setting("rawg_api_key"):
            st.info("Configure a RAWG API key first in Connections.")
        elif not games:
            st.info("No games to update.")
        else:
            missing_info = [g for g in games if not g.get("external_metadata_json")]
            
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
