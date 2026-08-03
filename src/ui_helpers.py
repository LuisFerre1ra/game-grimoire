from __future__ import annotations
import html as html_mod
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
import streamlit as st
import database as db

BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BASE_DIR / "assets"
LOGO_HORIZONTAL_WHITE_SVG = ASSETS_DIR / "logo-horizontal-white.svg"
LOGO_HORIZONTAL_WHITE_PNG = ASSETS_DIR / "logo-horizontal-white.png"
LOGO_HORIZONTAL_BLACK_SVG = ASSETS_DIR / "logo-horizontal-black.svg"
LOGO_HORIZONTAL_BLACK_PNG = ASSETS_DIR / "logo-horizontal-black.png"
LOGO_HORIZONTAL_SVG = LOGO_HORIZONTAL_WHITE_SVG if LOGO_HORIZONTAL_WHITE_SVG.exists() else ASSETS_DIR / "logo-horizontal.svg"
LOGO_HORIZONTAL_PNG = LOGO_HORIZONTAL_WHITE_PNG if LOGO_HORIZONTAL_WHITE_PNG.exists() else ASSETS_DIR / "logo-horizontal.png"
LOGO_MARK_SVG = ASSETS_DIR / "logo-mark.svg"
FAVICON_PNG = ASSETS_DIR / "favicon.png"

STATUS_LABELS = {"backlog": "Backlog", "played": "Played", "abandoned": "Abandoned"}

@st.cache_data(ttl=30)
def cached_list_tags() -> list[dict[str, Any]]:
    """Cached wrapper to avoid re-querying tags on every render."""
    return db.list_tags()

def clear_tags_cache() -> None:
    cached_list_tags.clear()

def queue_toast(message: str, icon: str = "") -> None:
    """Store a toast in session_state so it fires AFTER the next st.rerun().

    Call this instead of st.toast() whenever a st.rerun() follows immediately.
    The deferred toast is shown at the very start of the next render by
    show_queued_toasts(), before any rerun can clobber it.
    """
    if "pending_toasts" not in st.session_state:
        st.session_state["pending_toasts"] = []
    st.session_state["pending_toasts"].append({"message": message, "icon": icon})

def show_queued_toasts() -> None:
    """Display any toasts queued by queue_toast(). Call once at app startup."""
    for toast in st.session_state.pop("pending_toasts", []):
        if toast.get("icon"):
            st.toast(toast["message"], icon=toast["icon"])
        else:
            st.toast(toast["message"])

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
          [data-testid="stSidebar"] div[data-testid="stImage"] img,
          .app-logo img {
            aspect-ratio: auto !important;
            width: auto !important;
            max-width: 100% !important;
            height: auto !important;
            object-fit: contain !important;
            border-radius: 0 !important;
            margin: 0 auto;
            display: block;
          }
          /* Streamlit Logo Sizing Override */
          div:has([data-testid="stSidebarLogo"]) {
            width: 100%;
          }
          [data-testid="stSidebarLogo"] {
            image-rendering: pixelated;
            width: 100%;
            height: auto !important;
          }
          /* Header icon shown when sidebar is collapsed */
          img[data-testid="stHeaderLogo"] {
            width: 32px !important;
            height: 32px !important;
            min-width: 32px !important;
            min-height: 32px !important;
            image-rendering: pixelated !important;
            object-fit: contain !important;
          }
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
          /* Custom Sidebar Navigation & Fixed 250px Width when expanded */
          [data-testid="stSidebar"] {
            background-color: #0b1423;
            border-right: 1px solid #1a2536;
          }
          [data-testid="stSidebar"][aria-expanded="true"] {
            width: 250px !important;
            min-width: 250px !important;
            max-width: 250px !important;
          }
          /* Disable sidebar animation on close */
          [data-testid="stSidebar"][aria-expanded="false"],
          [data-testid="stSidebar"][aria-expanded="false"] * {
            transition: none !important;
            animation: none !important;
          }
          /* Completely remove sidebar resize handle (2nd child of stSidebar) */
          [data-testid="stSidebar"] > :nth-child(2),
          [data-testid="stSidebarResizer"],
          div[data-testid="stSidebarResizer"] {
            display: none !important;
            visibility: hidden !important;
            width: 0 !important;
            min-width: 0 !important;
            max-width: 0 !important;
            overflow: hidden !important;
            pointer-events: none !important;
            cursor: default !important;
            opacity: 0 !important;
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

          /* ── Toast Notifications ─────────────────────────────────────────── */

          @keyframes toast-slide-in {
            0%   { transform: translateX(120%); opacity: 0; }
            60%  { transform: translateX(-6px);  opacity: 1; }
            80%  { transform: translateX(3px);   opacity: 1; }
            100% { transform: translateX(0);     opacity: 1; }
          }

          @keyframes toast-glow-green {
            0%   { box-shadow: 0 4px 24px rgba(34,197,94,0.0),  0 2px 8px rgba(0,0,0,0.5); }
            40%  { box-shadow: 0 4px 32px rgba(34,197,94,0.55), 0 2px 8px rgba(0,0,0,0.5); }
            100% { box-shadow: 0 4px 16px rgba(34,197,94,0.2),  0 2px 8px rgba(0,0,0,0.4); }
          }

          @keyframes toast-glow-amber {
            0%   { box-shadow: 0 4px 24px rgba(251,191,36,0.0),  0 2px 8px rgba(0,0,0,0.5); }
            40%  { box-shadow: 0 4px 32px rgba(251,191,36,0.55), 0 2px 8px rgba(0,0,0,0.5); }
            100% { box-shadow: 0 4px 16px rgba(251,191,36,0.2),  0 2px 8px rgba(0,0,0,0.4); }
          }

          @keyframes toast-glow-red {
            0%   { box-shadow: 0 4px 24px rgba(239,68,68,0.0),  0 2px 8px rgba(0,0,0,0.5); }
            40%  { box-shadow: 0 4px 32px rgba(239,68,68,0.55), 0 2px 8px rgba(0,0,0,0.5); }
            100% { box-shadow: 0 4px 16px rgba(239,68,68,0.2),  0 2px 8px rgba(0,0,0,0.4); }
          }

          /* Base toast reset */
          div[data-testid="stToast"] {
            animation: toast-slide-in 0.45s cubic-bezier(0.22,1,0.36,1) forwards;
            border-radius: 0.6rem !important;
            border: 1px solid rgba(255,255,255,0.08) !important;
            backdrop-filter: blur(12px) !important;
            padding: 0.85rem 1.1rem !important;
            min-width: 280px !important;
            max-width: 380px !important;
            font-size: 0.9rem !important;
            font-weight: 500 !important;
            color: #f0f6ff !important;
          }

          div[data-testid="stToast"] p {
            color: #f0f6ff !important;
            font-size: 0.9rem !important;
            font-weight: 500 !important;
            line-height: 1.4 !important;
          }

          /* ── Green toasts: check_circle, restore, cloud_done ── */
          div[data-testid="stToast"]:has([data-testid="stIconMaterial"]) {
            background: linear-gradient(135deg, #0f2a1a 0%, #14381f 100%) !important;
            border-color: rgba(34,197,94,0.35) !important;
            animation: toast-slide-in 0.45s cubic-bezier(0.22,1,0.36,1) forwards,
                       toast-glow-green 1.2s 0.45s ease-out forwards !important;
          }

          div[data-testid="stToast"]:has([data-testid="stIconMaterial"]) [data-testid="stIconMaterial"] {
            color: #4ade80 !important;
          }

          /* ── Amber toasts: refresh, delete ── */
          div[data-testid="stToast"]:has([data-testid="stIconMaterial"][aria-label="refresh"]),
          div[data-testid="stToast"]:has([data-testid="stIconMaterial"][aria-label="delete"]) {
            background: linear-gradient(135deg, #251e08 0%, #352905 100%) !important;
            border-color: rgba(251,191,36,0.35) !important;
            animation: toast-slide-in 0.45s cubic-bezier(0.22,1,0.36,1) forwards,
                       toast-glow-amber 1.2s 0.45s ease-out forwards !important;
          }

          div[data-testid="stToast"]:has([data-testid="stIconMaterial"][aria-label="refresh"]) [data-testid="stIconMaterial"],
          div[data-testid="stToast"]:has([data-testid="stIconMaterial"][aria-label="delete"]) [data-testid="stIconMaterial"] {
            color: #fbbf24 !important;
          }

          /* ── Red toasts: error, cloud_off ── */
          div[data-testid="stToast"]:has([data-testid="stIconMaterial"][aria-label="error"]),
          div[data-testid="stToast"]:has([data-testid="stIconMaterial"][aria-label="cloud_off"]) {
            background: linear-gradient(135deg, #200d0d 0%, #2e1010 100%) !important;
            border-color: rgba(239,68,68,0.4) !important;
            animation: toast-slide-in 0.45s cubic-bezier(0.22,1,0.36,1) forwards,
                       toast-glow-red 1.2s 0.45s ease-out forwards !important;
          }

          div[data-testid="stToast"]:has([data-testid="stIconMaterial"][aria-label="error"]) [data-testid="stIconMaterial"],
          div[data-testid="stToast"]:has([data-testid="stIconMaterial"][aria-label="cloud_off"]) [data-testid="stIconMaterial"] {
            color: #f87171 !important;
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