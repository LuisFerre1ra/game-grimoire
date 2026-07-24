from __future__ import annotations
import html as html_mod
from typing import Any
import pandas as pd
import streamlit as st
from st_keyup import st_keyup
import database as db
from ui_helpers import cached_list_tags, format_hours, cover_reference, tag_html, readable_date
from dialogs import game_actions

def render_card(item: dict[str, Any], prefix: str, main_tags_names: set[str]) -> None:
    with st.container(border=True):
        cover = cover_reference(item)
        if cover:
            st.image(cover, width="stretch")
        else:
            st.markdown('<div class="game-placeholder">Sin cover</div>', unsafe_allow_html=True)
            st.markdown("<div style='margin-top: 0.5rem;'></div>", unsafe_allow_html=True)
            
        special_tags = [t for t in item["tags"] if t in main_tags_names]
        normal_tags = [t for t in item["tags"] if t not in main_tags_names]
        
        if special_tags:
            st.markdown(f"<div class='special-tags-container'>{tag_html(special_tags, limit=10, show_empty=False)}</div>", unsafe_allow_html=True)
            
        safe_title = html_mod.escape(item["title"])
        title_html = f'<div title="{safe_title}" style="display: -webkit-box; -webkit-line-clamp: 1; -webkit-box-orient: vertical; overflow: hidden; font-weight: bold; line-height: 1.4; height: 1.4em; margin-bottom: 0.5rem;">{safe_title}</div>'
        st.markdown(title_html, unsafe_allow_html=True)
        
        detail = format_hours(item.get("hours"))
        if item["status"] == "backlog" and item["ready_to_play"]:
            detail += " · Ready to play"
        st.markdown(f"<div style='font-size: 0.86rem; color: #9aa8ba; margin-bottom: 0.3rem;'>{detail}</div>", unsafe_allow_html=True)
        st.markdown(tag_html(normal_tags, limit=2) + "<div style='margin-bottom: 0.6rem;'></div>", unsafe_allow_html=True)
        game_actions(item, prefix)

def filter_and_sort(items: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    tags = cached_list_tags()
    with st.container(border=True):
        row1_col1, row1_col2, row1_col3 = st.columns([2, 1, 1], vertical_alignment="bottom")
        with row1_col1:
            query = st_keyup("Search by title", key=f"{key}_search")
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

    text = (query or "").strip().casefold()
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

    # Precompute main_tags_names once for all cards (PERF-04)
    all_tags = cached_list_tags()
    main_tags_names = {t["name"] for t in all_tags if t.get("is_main")}

    current = items[(page - 1) * page_size : page * page_size]
    st.caption(f"Mostrando {len(current)} de {len(items)} games")
    for start in range(0, len(current), 4):
        columns = st.columns(4)
        for column, item in zip(columns, current[start : start + 4]):
            with column:
                render_card(item, f"{key}_{item['id']}", main_tags_names)
                
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
        known_sum = sum(known) if known else 0.0
        predicted_total, margin = db.estimate_total_hours(known, missing)

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