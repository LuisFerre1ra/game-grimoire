from __future__ import annotations
import json
import time
from typing import Any
import pandas as pd
import streamlit as st
import database as db
from providers import ProviderError, get_ordered_providers
from ui_helpers import cached_list_tags
from dialogs import queue_dialog
from pages.add_games import enrich_one

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
        
        all_tags = cached_list_tags()
        existing_cats = sorted(list(set(t["category"] for t in all_tags if t.get("category"))))
        if not existing_cats:
            existing_cats = ["Genres", "Themes", "Game modes", "Age Rating", "Status", "Reviews", "Requirement", "Compatibility", "Other"]
        cat_options = existing_cats + ["+ New category..."]
        
        if st.button("+ Add new tag", type="primary"):
            try:
                db.add_tag(f"New tag {int(time.time() * 1000) % 10000}", "Other", "#7E8996", False)
                cached_list_tags.clear()
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
                
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
            h4.markdown("**Alias**")
            h5.markdown("<div style='text-align: center; font-weight: bold;'>Principal</div>", unsafe_allow_html=True)
            h6.markdown("<div style='text-align: center; font-weight: bold;'>Save</div>", unsafe_allow_html=True)
            h7.markdown("<div style='text-align: center; font-weight: bold;'>Delete</div>", unsafe_allow_html=True)

            for tag in all_tags:
                t_id = tag["id"]
                c1, c2, c3, c4, c5, c6, c7 = st.columns([2.4, 2.6, 0.6, 3.3, 0.8, 0.8, 0.8])

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
                new_aliases = c4.text_input("Alias", value=tag.get("aliases", ""), key=f"t_aliases_{t_id}", label_visibility="collapsed")

                with c5:
                    _, c_chk, _ = st.columns([1, 1.5, 1])
                    new_main = c_chk.checkbox("Sí", value=bool(tag.get("is_main", 0)), key=f"t_main_{t_id}", label_visibility="collapsed")

                # Explicit Save button only write to DB when the user clicks it
                with c6:
                    if st.button("", icon=":material/save:", key=f"save_{t_id}", use_container_width=True, help="Save changes"):
                        try:
                            db.update_tag(t_id, new_name, effective_cat, new_color, new_main, new_aliases)
                            cached_list_tags.clear()
                            st.toast(f"«{new_name}» guardado", icon=":material/check_circle:")
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
                to_update = all_games
                
            if to_update:
                progress = st.progress(0, text="Actualizando datos…")
                results: list[str] = []
                for number, item in enumerate(to_update, start=1):
                    try:
                        results.append(f"{item['title']}: {enrich_one(item['id'], item['title'])}")
                    except Exception as exc:
                        results.append(f"{item['title']}: {exc}")
                    progress.progress(number / len(to_update), text=f"Actualizando {number} de {len(to_update)}…")
                progress.empty()
                cached_list_tags.clear()

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