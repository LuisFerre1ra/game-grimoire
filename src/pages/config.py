from __future__ import annotations
import json
import time
from typing import Any
import pandas as pd
import streamlit as st
import database as db
from providers import ProviderError, get_ordered_providers
from ui_helpers import cached_list_tags, queue_toast, LOGO_HORIZONTAL_SVG, LOGO_MARK_SVG
from dialogs import queue_dialog
from pages.add_games import enrich_one

def configuration_page() -> None:
    st.title("Settings")
    connection_tab, tags_tab, enrichment_tab, export_tab, about_tab = st.tabs(["Connections", "Tags", "Update catalogue", "Export", "About"])
    with connection_tab:
        st.subheader("Optional services")
        st.caption("The app works without external services; providers are only queried on request.")
        with st.expander("How to get API credentials"):
            st.markdown(
                "**RAWG** — Free API key after creating an account.\n"
                "1. Go to [rawg.io/apidocs](https://rawg.io/apidocs) and create a free account.\n"
                "2. Your API key is shown on that page after login. Copy it into the field below.\n\n"
                "**IGDB** — uses Twitch for authentication (the credentials come from Twitch, not IGDB directly).\n"
                "1. Log in or register at [dev.twitch.tv/console](https://dev.twitch.tv/console).\n"
                "2. Create a new application (any name, set OAuth redirect to `http://localhost`).\n"
                "3. Copy the **Client ID** shown on the app page.\n"
                "4. Click *New Secret* to generate a **Client Secret**.\n"
                "5. Paste both into the fields below. The access token is fetched and refreshed automatically."
            )
        with st.form("connections"):
            current_val = db.get_setting("provider_priority", "IGDB,RAWG")
            default_selection = [p for p in current_val.split(",") if p in ["IGDB", "RAWG"]]
            
            provider_order_list = st.multiselect(
                "Provider priority order (select in order of preference)",
                options=["IGDB", "RAWG"],
                default=default_selection,
                help="Providers are tried in this order. If the first one returns no results for a game, the next one is used as fallback.",
            )
            rawg_key = st.text_input(
                "RAWG API Key",
                value=db.get_setting("rawg_api_key"),
                type="password",
                help="Get a free key at rawg.io/apidocs. Only queried when you request metadata.",
            )
            igdb_id = st.text_input(
                "IGDB Client ID",
                value=db.get_setting("igdb_client_id"),
                help="Issued by Twitch (dev.twitch.tv/console). IGDB uses Twitch for authentication — see the guide above.",
            )
            igdb_secret = st.text_input(
                "IGDB Client Secret",
                value=db.get_setting("igdb_client_secret"),
                type="password",
                help="Generated alongside the Client ID in your Twitch developer app. Access tokens are refreshed automatically.",
            )
            saved = st.form_submit_button("Save settings")
        if saved:
            db.set_setting("provider_priority", ",".join(provider_order_list))
            db.set_setting("rawg_api_key", rawg_key.strip())
            db.set_setting("igdb_client_id", igdb_id.strip())
            db.set_setting("igdb_client_secret", igdb_secret.strip())
            st.toast("Settings saved", icon=":material/check_circle:")
    with tags_tab:
        st.subheader("Tag catalogue")
        
        all_tags = cached_list_tags()
        existing_cats = sorted(list(set(t["category"] for t in all_tags if t.get("category"))))
        if not existing_cats:
            existing_cats = ["Genres", "Themes", "Game modes", "Age Rating", "Status", "Reviews", "Requirements", "Compatibility", "Other"]
        cat_options = existing_cats + ["+ New category..."]
        
        top_left, _, top_right1, top_right2 = st.columns([1.5, 3.5, 1.8, 1.8])
        with top_left:
            if st.button("+ Add new tag", type="primary", use_container_width=True):
                try:
                    db.add_tag(f"New tag {int(time.time() * 1000) % 10000}", "Other", "#7E8996", False)
                    cached_list_tags.clear()
                    queue_toast("New tag added — rename it in the list below", icon=":material/check_circle:")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
        with top_right1:
            if st.button("Restore missing", type="secondary", use_container_width=True, help="Restore missing default tags & aliases"):
                queue_dialog("restore_missing_tags", 0)
        with top_right2:
            if st.button("Reset defaults", type="secondary", use_container_width=True, help="Reset default tags to factory settings"):
                queue_dialog("reset_default_tags", 0)
                
        all_tags = cached_list_tags()
        
        if "tag_order" not in st.session_state:
            st.session_state["tag_order"] = [t["id"] for t in all_tags]
            
        known_ids = set(st.session_state["tag_order"])
        new_tags = [t["id"] for t in all_tags if t["id"] not in known_ids]
        if new_tags:
            st.session_state["tag_order"] = new_tags + list(st.session_state["tag_order"])
        
        order_map = {tid: i for i, tid in enumerate(st.session_state["tag_order"])}
        all_tags.sort(key=lambda t: order_map.get(t["id"], 999999))

        if all_tags:
            h1, h2, h3, h4, h5, h6, h7 = st.columns([2.4, 2.6, 0.6, 3.3, 0.8, 0.8, 0.8])
            h1.markdown("**Name**")
            h2.markdown("**Category**")
            h3.markdown("**Color**")
            h4.markdown("**Aliases**", help="Comma-separated alternative names. When importing game details from IGDB or RAWG, any provider tags matching these aliases will automatically map to this local tag.")
            h5.markdown("**Main**", help="Tags marked as Main are featured prominently directly on game cover cards in your collection grid, allowing you to quickly spot them at a glance.")
            h6.markdown("<div class='col-header-center'>Save</div>", unsafe_allow_html=True)
            h7.markdown("<div class='col-header-center'>Delete</div>", unsafe_allow_html=True)

            for tag in all_tags:
                t_id = tag["id"]
                c1, c2, c3, c4, c5, c6, c7 = st.columns([2.4, 2.6, 0.6, 3.3, 0.8, 0.8, 0.8])

                new_name = c1.text_input("Name", value=tag["name"], key=f"t_name_{t_id}", label_visibility="collapsed")

                current_cat = tag["category"]
                cat_idx = cat_options.index(current_cat) if current_cat in cat_options else 0
                cat_val = c2.selectbox("Category", cat_options, index=cat_idx, key=f"t_cat_sel_{t_id}", label_visibility="collapsed")
                if cat_val == "+ New category...":
                    new_cat = c2.text_input("New category", value="", key=f"t_cat_new_{t_id}", label_visibility="collapsed", placeholder="Type here...")
                else:
                    new_cat = cat_val
                effective_cat = tag["category"] if (cat_val == "+ New category..." and not new_cat.strip()) else new_cat.strip()

                new_color = c3.color_picker("Color", value=tag["color"], key=f"t_col_{t_id}", label_visibility="collapsed")
                new_aliases = c4.text_input("Aliases", value=tag.get("aliases", ""), key=f"t_aliases_{t_id}", label_visibility="collapsed")

                with c5:
                    _, c_chk, _ = st.columns([1, 1.5, 1])
                    new_main = c_chk.checkbox("Yes", value=bool(tag.get("is_main", 0)), key=f"t_main_{t_id}", label_visibility="collapsed")

                # Explicit Save button only write to DB when the user clicks it
                with c6:
                    if st.button("", icon=":material/save:", key=f"save_{t_id}", use_container_width=True, help="Save changes"):
                        try:
                            db.update_tag(t_id, new_name, effective_cat, new_color, new_main, new_aliases)
                            cached_list_tags.clear()
                            queue_toast(f"'{new_name}' saved", icon=":material/check_circle:")
                            st.rerun()
                        except ValueError as exc:
                            st.error(str(exc))

                with c7:
                    st.markdown('<div class="delete-btn-wrapper"></div>', unsafe_allow_html=True)
                    if st.button("", icon=":material/delete:", key=f"del_{t_id}", type="secondary", use_container_width=True, help="Delete tag"):
                        queue_dialog("delete_tag", t_id)

    with enrichment_tab:
        st.subheader("Update missing data")
        if not get_ordered_providers():
            st.info("Configure a provider first (IGDB or RAWG) in Connections.")
        else:
            all_games = db.list_games()
            missing_info = db.get_games_missing_provider_data()
            
            c1, c2 = st.columns(2)
            c1.metric("Games in library", len(all_games))
            c2.metric("Games without info", len(missing_info))
            
            st.write("### Update options")
            st.write("**Option A: Fetch missing data**\nFetches details and covers only for games that have no information yet.")
            btn_missing = st.button("Fetch missing data", disabled=len(missing_info) == 0, type="primary")
            
            st.write("**Option B: Full update**\nRe-downloads information for all your games. Useful to refresh ratings or covers.")
            btn_all = st.button("Update entire collection")
            
            to_update = []
            if btn_missing:
                to_update = missing_info
            elif btn_all:
                to_update = all_games
                
            if to_update:
                progress = st.progress(0, text="Updating data...")
                results: list[str] = []
                for number, item in enumerate(to_update, start=1):
                    try:
                        results.append(f"{item['title']}: {enrich_one(item['id'], item['title'])}")
                    except Exception as exc:
                        results.append(f"{item['title']}: {exc}")
                    progress.progress(number / len(to_update), text=f"Updating {number} of {len(to_update)}...")
                progress.empty()
                cached_list_tags.clear()
                st.toast(f"Updated {len(to_update)} game(s)", icon=":material/cloud_done:")
                with st.expander("View detailed results"):
                    st.write("\n\n".join(results))
    with export_tab:
        st.subheader("Local exports")
        rows = db.export_rows()
        frame = pd.DataFrame(rows)
        st.download_button("Download CSV", frame.to_csv(index=False).encode("utf-8-sig"), "game_grimoire_export.csv", "text/csv")
        st.caption("All games with their status, hours, tags (comma-separated), release date, date added, and years played.")
        st.download_button("Download JSON", json.dumps(rows, ensure_ascii=False, indent=2).encode("utf-8"), "game_grimoire_export.json", "application/json")
        st.caption("Same data as CSV in structured JSON format, one object per game.")
        if db.DB_PATH.exists():
            st.download_button("Download SQLite database", db.DB_PATH.read_bytes(), "game_grimoire_backup.db", "application/octet-stream")
            st.caption("Full backup of the local database, including all settings, tags, aliases, and play history.")

    with about_tab:
        st.subheader("About Game Grimoire")
        col_logo, col_info = st.columns([1, 2], vertical_alignment="center")
        with col_logo:
            if LOGO_HORIZONTAL_SVG.exists():
                st.image(str(LOGO_HORIZONTAL_SVG), use_container_width=True)
            elif LOGO_MARK_SVG.exists():
                st.image(str(LOGO_MARK_SVG), width=120)
        with col_info:
            st.markdown("""
            **Game Grimoire** is a local-first game collection manager designed for speed, privacy, and simplicity.
            
            - **Version**: 1.0.0
            - **Storage**: SQLite local database
            - **Database Path**: `{}`
            """.format(db.DB_PATH))