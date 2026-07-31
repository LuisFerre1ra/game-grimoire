from __future__ import annotations
import html as html_mod
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
import streamlit as st
import database as db

STATUS_LABELS = {"backlog": "Backlog", "played": "Played", "abandoned": "Abandoned"}

@st.cache_data(ttl=30)
def cached_list_tags() -> list[dict[str, Any]]:
    """Cached wrapper to avoid re-querying tags on every render."""
    return db.list_tags()

def clear_tags_cache() -> None:
    cached_list_tags.clear()

def inject_styles() -> None:
    st.markdown(
        """
        <style>
          .block-container { max-width: 1500px; padding-top: 1.4rem; }
          .game-placeholder {aspect-ratio: 3 / 4; width: 100%; display:flex; flex-direction:column; align-items:center;
            justify-content:center; border-radius:.55rem; color:#d7e3f5; background:linear-gradient(145deg,#24334d,#121b2b); font-size:.9rem;}
          .game-placeholder small {font-size:.78rem; margin-top:.55rem; color:#aebed2;}
          .tag-chip {display:inline-block; margin:.2rem .4rem .2rem 0; padding:.12rem .55rem; border-radius:999px;
            background:#27374d; color:#ffffff; font-size:.78rem; font-weight:500; text-shadow:0px 1px 2px rgba(0,0,0,0.6);}
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
          .special-tags-container .tag-chip {
            box-shadow: 0px 2px 5px rgba(0, 0, 0, 0.7);
          }
          /* Custom Sidebar Navigation */
          [data-testid="stSidebar"][aria-expanded="true"] {
            width: 240px;
          }
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
            align-items: center;
            gap: 0.6rem;
            padding: 0.6rem 0.8rem;
            border-radius: 0.4rem;
            transition: all 0.2s ease;
            box-shadow: none;
          }
          [data-testid="stSidebar"] [data-testid="stButton"] button:hover {
            background-color: #172439;
            color: #ffffff;
          }
          [data-testid="stSidebar"] [data-testid="stButton"] button > * {
            transition: transform 0.2s ease;
          }
          [data-testid="stSidebar"] [data-testid="stButton"] button:hover > * {
            transform: scale(1.05);
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
    path_str = item.get("cover_local_path")
    if path_str:
        # Check in AppData covers directory (%APPDATA%\GameGrimoire\covers\<filename>)
        filename = Path(path_str).name
        candidate_appdata = db.DATA_DIR / "covers" / filename
        if candidate_appdata.exists():
            return str(candidate_appdata)

        # Fallback: check relative to BASE_DIR if legacy path
        candidate_base = db.BASE_DIR / path_str
        if candidate_base.exists():
            return str(candidate_base)
    return item.get("cover_source_url")

def tag_html(tags: Iterable[str], limit: int = 4, show_empty: bool = True) -> str:
    names = list(tags)
    shown = names[:limit]
    hidden = names[limit:]
    
    all_tags = cached_list_tags()
    name_to_color = {t["name"]: t["color"] for t in all_tags}
    
    chips = []
    for name in shown:
        safe_name = html_mod.escape(name)
        safe_color = html_mod.escape(name_to_color.get(name, "#27374d"))
        chips.append(f'<span class="tag-chip" style="background-color: {safe_color}; white-space: nowrap; text-overflow: ellipsis; max-width: 150px; overflow: hidden;">{safe_name}</span>')
        
    if hidden:
        hidden_chips = []
        for name in hidden:
            safe_name = html_mod.escape(name)
            safe_color = html_mod.escape(name_to_color.get(name, "#27374d"))
            hidden_chips.append(f'<span class="tag-chip" style="background-color: {safe_color}; margin-bottom: 0.2rem;">{safe_name}</span>')
            
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