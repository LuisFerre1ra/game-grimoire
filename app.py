"""Local game library application."""

from __future__ import annotations

from datetime import datetime

import streamlit as st

import database as db
from ui_helpers import inject_styles
from dialogs import show_pending_dialog
from pages.inventory import inventory_page
from pages.add_games import add_games_page
from pages.config import configuration_page

st.set_page_config(page_title="My Game Library", layout="wide")
db.init_database()

def main() -> None:
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
    current_year = datetime.now().year
    with st.sidebar:
        st.markdown("<h2 style='text-align: center; margin-bottom: 2rem; color: #e6eefb; font-weight: 700; letter-spacing: 0.5px;'>Library</h2>", unsafe_allow_html=True)
        for item in nav_items:
            p = item["name"]
            icon = item["icon"]
            if st.button(p, icon=icon, key=f"nav_{p}", use_container_width=True, type="primary" if page == p else "secondary"):
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