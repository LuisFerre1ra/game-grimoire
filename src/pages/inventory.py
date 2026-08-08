from __future__ import annotations

import html as html_mod
from typing import Any

import pandas as pd
import streamlit as st
from st_keyup import st_keyup

import database as db
from dialogs import game_actions
from ui_helpers import (
    ICON_BAN,
    ICON_BOLT,
    ICON_CHECK,
    cached_list_tags,
    cover_reference,
    format_hours,
    readable_date,
    status_tag_html,
    tag_html,
)


def render_card(item: dict[str, Any], prefix: str, main_tags_names: set[str]) -> None:
    status = item.get("status", "backlog")
    card_marker = "status-played-card" if status == "played" else ("status-abandoned-card" if status == "abandoned" else "status-backlog-card")
    with st.container(border=True):
        st.markdown(f'<div class="{card_marker}"></div>', unsafe_allow_html=True)

        cover = cover_reference(item)
        if cover:
            st.image(cover, width="stretch")
        else:
            st.markdown('<div class="game-placeholder">No cover</div>', unsafe_allow_html=True)
            st.markdown("<div style='margin-top: 0.5rem;'></div>", unsafe_allow_html=True)

        # Status tag rendered AFTER image so absolute positioning overlays it from top-left
        status_tag = status_tag_html(status, item.get("ready_to_play", False))
        if status_tag:
            st.markdown(f'<div class="status-tags-container">{status_tag}</div>', unsafe_allow_html=True)

        special_tags = [t for t in item["tags"] if t in main_tags_names]
        normal_tags = [t for t in item["tags"] if t not in main_tags_names]
        
        if special_tags:
            st.markdown(f"<div class='special-tags-container'>{tag_html(special_tags, limit=10, show_empty=False)}</div>", unsafe_allow_html=True)
            
        safe_title = html_mod.escape(item["title"])
        title_html = f'<div title="{safe_title}" class="card-title">{safe_title}</div>'
        st.markdown(title_html, unsafe_allow_html=True)
        
        detail = format_hours(item.get("hours"))
        if status == "played":
            detail += f" · <span class='status-inline-played'>{ICON_CHECK} Played</span>"
        elif status == "abandoned":
            detail += f" · <span class='status-inline-abandoned'>{ICON_BAN} Abandoned</span>"
        elif status == "backlog" and item.get("ready_to_play"):
            detail += f" · <span class='status-inline-ready'>{ICON_BOLT} Ready to play</span>"

        st.markdown(f"<div class='card-detail'>{detail}</div>", unsafe_allow_html=True)
        st.markdown(tag_html(normal_tags, limit=2) + "<div style='margin-bottom: 0.6rem;'></div>", unsafe_allow_html=True)
        game_actions(item, prefix)


def filter_and_sort(items: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    tags = cached_list_tags()
    with st.container(border=True):
        row1_col1, row1_col2, row1_col3 = st.columns([2, 1, 1], vertical_alignment="top")
        with row1_col1:
            query = st_keyup("Search by title", key=f"{key}_search")
        wanted_tags = row1_col2.multiselect(
            "Tags (include)",
            [tag["name"] for tag in tags],
            key=f"{key}_tags",
            help="Only shows games that have ALL of the selected tags.",
        )
        excluded_tags = row1_col3.multiselect(
            "Tags (exclude)",
            [tag["name"] for tag in tags],
            key=f"{key}_tags_exc",
            help="Hides games that have ANY of the selected tags.",
        )
        
        row2_col1, row2_col2, row2_col3 = st.columns([2, 1, 1], vertical_alignment="bottom")
        with row2_col1:
            duration_category = st.radio("Duration", ["All", "Short (<10h)", "Medium (10-30h)", "Long (30h+)"], horizontal=True, key=f"{key}_duration")
        
        if key == "played":
            status_filter = row2_col2.selectbox("Status", ["All", "Played", "Abandoned"], key=f"{key}_status_filter")
            only_ready = False
        else:
            status_filter = "All"
            only_ready = row2_col2.checkbox(
                "Ready to play only",
                key=f"{key}_ready",
                disabled=key != "backlog",
                help="Shows only games you have marked as installed and ready to launch.",
            )

        include_unknown = row2_col3.checkbox(
            "Include without duration",
            value=True,
            key=f"{key}_unknown",
            help="Duration is the playtime in hours. When unchecked, games with no hours entered are hidden from results.",
        )

        sort_col, direction, view_col = st.columns([2, 1, 1], vertical_alignment="bottom")
        sort_label = sort_col.selectbox("Sort by", ["Title", "Hours", "Date added", "Release date"], key=f"{key}_sort")
        descending = direction.toggle("Descending", key=f"{key}_descending")
        view = view_col.radio("View", ["Cards", "Table"], horizontal=True, key=f"{key}_view")

    def match_duration(hours: float | None) -> bool:
        if duration_category == "All": return True
        if hours is None: return True
        h = float(hours)
        if duration_category == "Short (<10h)" and h < 10: return True
        if duration_category == "Medium (10-30h)" and 10 <= h < 30: return True
        return bool(duration_category == "Long (30h+)" and h >= 30)

    text = (query or "").strip().casefold()
    filtered = [
        item for item in items
        if (not text or text in item["title"].casefold())
        and (not wanted_tags or set(wanted_tags).issubset(item["tags"]))
        and (not excluded_tags or not set(excluded_tags).intersection(item["tags"]))
        and (not only_ready or item["ready_to_play"])
        and (status_filter == "All" or (status_filter == "Played" and item["status"] == "played") or (status_filter == "Abandoned" and item["status"] == "abandoned"))
        and (include_unknown or item["hours"] is not None)
        and match_duration(item["hours"])
    ]
    fields = {"Title": "title", "Hours": "hours", "Date added": "added_at", "Release date": "release_date"}
    field = fields[sort_label]
    present = [item for item in filtered if item.get(field) is not None]
    missing = [item for item in filtered if item.get(field) is None]
    present.sort(key=lambda item: item["title"].casefold() if field == "title" else item[field], reverse=descending)
    st.session_state[f"{key}_active_view"] = view
    return present + missing


def render_cards(items: list[dict[str, Any]], key: str) -> None:
    page_size = st.select_slider("Games per page", options=[12, 24, 36, 48], value=24, key=f"{key}_page_size")
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
        col2.markdown(f"<div class='pagination-label'><b>Page {page} of {pages}</b></div>", unsafe_allow_html=True)
        if col3.button(">", key=f"{key}_next_{suffix}", disabled=page >= pages, use_container_width=True):
            st.session_state[page_state_key] += 1
            st.rerun()

    render_pagination("top")

    # Precompute main_tags_names once for all cards (PERF-04)
    all_tags = cached_list_tags()
    main_tags_names = {t["name"] for t in all_tags if t.get("is_main")}

    current = items[(page - 1) * page_size : page * page_size]
    st.caption(f"Showing {len(current)} of {len(items)} games")
    for start in range(0, len(current), 4):
        columns = st.columns(4)
        for column, item in zip(columns, current[start : start + 4]):
            with column:
                render_card(item, f"{key}_{item['id']}", main_tags_names)
                
    render_pagination("bottom")

def render_table(items: list[dict[str, Any]], key: str) -> None:
    rows = [{
        "Title": item["title"],
        "Status": "Played" if item["status"] == "played" else ("Abandoned" if item["status"] == "abandoned" else "Backlog"),
        "Hours": item["hours"],
        "Ready": "Yes" if item["ready_to_play"] else "—",
        "Tags": ", ".join(item["tags"]),
        "Release": readable_date(item.get("release_date")),
        "Added": readable_date(item.get("added_at")),
        "Years played": ", ".join(map(str, sorted(set(item["years"])))),
    } for item in items]
    event = st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row", key=f"{key}_table", column_config={"Hours": st.column_config.NumberColumn(format="%.1f h")})
    selected_rows = event.selection.rows if event and event.selection.rows else []
    if selected_rows:
        chosen = items[selected_rows[0]]
        left, right = st.columns([5, 1])
        left.info(f"Selected: **{chosen['title']}** ({chosen['status'].capitalize()})")
        with right:
            game_actions(chosen, f"{key}_table_{chosen['id']}")
    else:
        st.caption("Select a row to open its actions.")

def inventory_page(title: str, statuses: list[str], key: str) -> None:
    st.title(title)
    if key == "played":
        st.caption("Includes both finished games and abandoned ones.")
    items = db.list_games(statuses)
    if key in ("backlog", "played"):
        known = [float(item["hours"]) for item in items if item.get("hours") is not None]
        missing = len(items) - len(known)
        known_sum = sum(known) if known else 0.0
        predicted_total, margin = db.estimate_total_hours(known, missing)

        if key == "played":
            played_cnt = sum(1 for i in items if i["status"] == "played")
            abandoned_cnt = sum(1 for i in items if i["status"] == "abandoned")
            a, b, c, d = st.columns(4)
            a.metric("Played (Finished)", played_cnt)
            b.metric("Abandoned", abandoned_cnt)
            c.metric("Known Hours", f"{known_sum:.1f} h")
            d.metric(
                "Estimated Hours",
                "\u2014" if predicted_total is None else f"{predicted_total:.1f} h",
                help="Projected total hours using a statistical estimate from games with known durations (80% confidence interval).",
            )
        else:
            a, b, c = st.columns(3)
            a.metric("Games", len(items))
            b.metric("Known Hours", f"{known_sum:.1f} h")
            c.metric(
                "Estimated Hours",
                "\u2014" if predicted_total is None else f"{predicted_total:.1f} h",
                help="Projected total hours using a statistical estimate from games with known durations (80% confidence interval).",
            )

        if margin is not None:
            st.caption(f"80% estimate: ± {margin:.1f} h · {missing} games without duration.")
    if not items:
        st.info("No games here yet. Add titles from 'Add Games'.")
        return
    shown = filter_and_sort(items, key)
    st.caption(f"{len(shown)} game(s) match the filters.")
    if st.session_state.get(f"{key}_active_view", "Cards") == "Cards":
        render_cards(shown, key)
    else:
        render_table(shown, key)