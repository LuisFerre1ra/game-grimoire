"""Game Grimoire - Local game library application."""

from __future__ import annotations

import streamlit as st

import database as db
from ui_helpers import (
    inject_styles,
    show_queued_toasts,
    FAVICON_PNG,
    LOGO_HORIZONTAL_SVG,
    LOGO_MARK_SVG,
)
from dialogs import show_pending_dialog
from pages.inventory import inventory_page
from pages.add_games import add_games_page
from pages.config import configuration_page

page_icon = str(FAVICON_PNG) if FAVICON_PNG.exists() else "🎮"
st.set_page_config(page_title="Game Grimoire", page_icon=page_icon, layout="wide")
db.init_database()

if hasattr(st, "logo") and LOGO_HORIZONTAL_SVG.exists():
    st.logo(
        image=str(LOGO_HORIZONTAL_SVG),
        icon_image=str(LOGO_MARK_SVG) if LOGO_MARK_SVG.exists() else None,
    )

def main() -> None:
    show_queued_toasts()
    inject_styles()
    nav_items = [
        {"name": "Backlog", "icon": ":material/inventory_2:"},
        {"name": "Played", "icon": ":material/sports_esports:"},
        {"name": "Add Games", "icon": ":material/add_circle:"},
        {"name": "Settings", "icon": ":material/settings:"},
    ]
    if "page" not in st.session_state:
        st.session_state["page"] = "Backlog"
        
    page = st.session_state["page"]
    with st.sidebar:
        for item in nav_items:
            p = item["name"]
            icon = item["icon"]
            if st.button(p, icon=icon, key=f"nav_{p}", use_container_width=True, type="primary" if page == p else "secondary"):
                st.session_state["page"] = p
                st.rerun()

    if page == "Backlog": inventory_page("Backlog", ["backlog"], "backlog")
    elif page == "Played": inventory_page("Played & Abandoned", ["played", "abandoned"], "played")
    elif page == "Add Games": add_games_page()
    elif page == "Settings": configuration_page()
    show_pending_dialog()

if __name__ == "__main__":
    main()